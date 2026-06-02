from django.db import models
from django.db import IntegrityError
from django.utils import timezone
from django.utils.timezone import now
import secrets
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinValueValidator
from django.db.models import Q

from users.models import Customer

def generate_plan_id():
    """Generates a random 10-digit saving plan ID."""
    return "".join(secrets.choice("0123456789") for _ in range(10))


class SavingType(models.Model):
    name = models.CharField(max_length=50)
    duration_months = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )  # 3, 6, 12
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )  # 0.05, 0.1, 0.15
    is_flexible = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        if not self.is_flexible and self.duration_months is None:
            raise ValidationError({"duration_months": "Fixed-term saving types must have a duration in months."})
        if self.is_flexible and self.duration_months is not None:
            raise ValidationError({"duration_months": "Flexible saving types should not set a fixed duration."})

    def save(self, *args, **kwargs):
        self.full_clean()
        # Track old rate so we can append a new history row when rate changes.
        old_rate = None
        if self.pk:
            old_rate = SavingType.objects.filter(pk=self.pk).values_list("interest_rate", flat=True).first()

        super().save(*args, **kwargs)

        # Create initial/open history if missing (first save path).
        open_row = self.rate_history.filter(effective_to__isnull=True).order_by("-effective_from").first()
        if open_row is None:
            SavingTypeRateHistory.objects.create(
                saving_type=self,
                interest_rate=self.interest_rate,
                effective_from=now().date(),
                effective_to=None,
            )
            return

        # If rate changed, close current row and open a new one from today.
        if old_rate is not None and old_rate != self.interest_rate:
            today = now().date()
            open_row.effective_to = today
            open_row.save(update_fields=["effective_to"])
            SavingTypeRateHistory.objects.create(
                saving_type=self,
                interest_rate=self.interest_rate,
                effective_from=today,
                effective_to=None,
            )

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="savingtype_duration_matches_flexibility",
                check=(
                    (Q(is_flexible=True) & Q(duration_months__isnull=True))
                    | (Q(is_flexible=False) & Q(duration_months__isnull=False))
                ),
            ),
        ]

class SavingTypeRateHistory(models.Model):
    # Keep a timeline of rates so flexible saving plans can calculate past periods correctly.
    saving_type = models.ForeignKey(SavingType, on_delete=models.CASCADE, related_name="rate_history")
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)  # null means "still active"

    class Meta:
        ordering = ["effective_from"]

class SavingPlanStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACTIVE = "ACTIVE", "Active"
    CLOSED = "CLOSED", "Closed"

class SavingPlan(models.Model):
    plan_id = models.CharField(
        primary_key=True,
        max_length=10,
        default=generate_plan_id,
        editable=False
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=10, choices=SavingPlanStatus.choices, default=SavingPlanStatus.PENDING)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    ) # snapshot
    start_date = models.DateField(null=True, blank=True) # lazy evaluation
    maturity_date = models.DateField(null=True, blank=True)  # allow null for non-fixed-term saving plans
    # For flexible saving plans, this tracks the last day we already accrued interest up to.
    interest_last_applied_on = models.DateField(null=True, blank=True)

    saving_type = models.ForeignKey(SavingType, on_delete=models.PROTECT, related_name="saving_plans")
    customer = models.ForeignKey(Customer, null=True, on_delete=models.SET_NULL, related_name='saving_plans')

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("Deposit amount must be greater than 0")
        self.__class__.objects.filter(pk=self.pk).update(balance=models.F("balance") + amount)
        self.refresh_from_db(fields=["balance"])

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("Withdrawal amount must be greater than 0")
        updated = self.__class__.objects.filter(pk=self.pk, balance__gte=amount).update(balance=models.F("balance") - amount)
        if updated == 0:
            raise ValueError("Insufficient balance")
        self.refresh_from_db(fields=["balance"])

    def update_status(self):
        if self.status != SavingPlanStatus.PENDING:
            raise ValidationError("Only pending saving plans can be activated.")

        self.status = SavingPlanStatus.ACTIVE
        self.start_date = now().date()
        self.save(update_fields=["status", "start_date"])

    def soft_delete(self):
        if self.status == SavingPlanStatus.ACTIVE:
            self.status = SavingPlanStatus.CLOSED
            self.deactivated_at = timezone.now()
            self.save(update_fields=["status", "deactivated_at"])

    def save(self, *args, **kwargs):
        if not self.pk:
            self.pk = generate_plan_id()

        for attempt in range(5):
            try:
                self.full_clean()
                return super().save(*args, **kwargs)
            except IntegrityError:
                if not self._state.adding or attempt == 4:
                    raise
                self.pk = generate_plan_id()

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="savingplan_balance_nonnegative",
                condition=Q(balance__gte=0),
            ),
        ]

class TransactionType(models.TextChoices):
    OPEN = "OPEN", "Saving Plan Opening"
    DEPOSIT = "DEPOSIT", "Deposit"
    WITHDRAW = "WITHDRAW", "Withdrawal"
    CLOSE = "CLOSE", "Saving Plan Closing"

class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    CANCELED = "CANCELED", "Canceled"

class Transaction(models.Model):
    transaction_type = models.CharField(max_length=10, choices=TransactionType.choices)
    status = models.CharField(max_length=10, choices=TransactionStatus.choices, default=TransactionStatus.PENDING,)
    balance_before = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    saving_plan = models.ForeignKey(SavingPlan, on_delete=models.PROTECT, related_name='transactions')

    def update_status(self, is_success: bool = False):
        if self.status != TransactionStatus.PENDING:
            raise ValidationError("Only pending transactions can be updated.")

        self.status = TransactionStatus.SUCCESS if is_success else TransactionStatus.CANCELED
        self.save(update_fields=["status"])

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="transaction_amount_positive_for_deposit_withdraw",
                condition=(
                    Q(transaction_type__in=[TransactionType.DEPOSIT, TransactionType.WITHDRAW], amount__gt=0)
                    | Q(transaction_type__in=[TransactionType.OPEN, TransactionType.CLOSE], amount__gte=0)
                ),
            ),
            models.CheckConstraint(
                name="transaction_balances_nonnegative",
                condition=Q(balance_before__gte=0) & Q(balance_after__gte=0),
            ),
        ]


class Parameter(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=255)
