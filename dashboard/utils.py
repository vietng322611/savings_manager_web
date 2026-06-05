from decimal import Decimal, InvalidOperation

from django.db import transaction

from savings.models import Parameter

PARAMETER_DEFINITIONS = (
    {
        "key": "min_initial_deposit",
        "label": "Minimum Initial Deposit",
        "description": "Minimum amount required when a customer opens a saving plan.",
        "input_type": "number",
        "step": "0.01",
        "min": "0.01",
        "kind": "decimal",
    },
    {
        "key": "min_additional_deposit",
        "label": "Minimum Additional Deposit",
        "description": "Minimum amount allowed for each deposit into a flexible saving plan.",
        "input_type": "number",
        "step": "0.01",
        "min": "0.01",
        "kind": "decimal",
    },
    {
        "key": "min_deposit_days_flexible",
        "label": "Flexible Withdrawal Lock Days",
        "description": "Number of days a flexible deposit must remain before withdrawal is allowed.",
        "input_type": "number",
        "step": "1",
        "min": "1",
        "kind": "integer",
    },
)

PARAMETER_DEFAULTS = {
    "min_initial_deposit": "1000000",
    "min_additional_deposit": "100000",
    "min_deposit_days_flexible": "15",
}


def get_parameter(key: str, default=None):
    try:
        return Parameter.objects.get(key=key).value
    except Parameter.DoesNotExist:
        return default


def get_parameter_definitions():
    return PARAMETER_DEFINITIONS


def get_parameter_rows(values=None, errors=None):
    values = values or {}
    errors = errors or {}
    stored_values = {
        parameter.key: parameter.value
        for parameter in Parameter.objects.filter(key__in=PARAMETER_DEFAULTS.keys())
    }

    rows = []
    for definition in PARAMETER_DEFINITIONS:
        key = definition["key"]
        rows.append({
            **definition,
            "value": values.get(key, stored_values.get(key, PARAMETER_DEFAULTS[key])),
            "error": errors.get(key),
        })

    return rows


def update_parameters(values):
    normalized_values = {}
    errors = {}

    for definition in PARAMETER_DEFINITIONS:
        key = definition["key"]
        raw_value = str(values.get(key, "")).strip()

        if not raw_value:
            errors[key] = "This value is required."
            continue

        if definition["kind"] == "integer":
            normalized_value = _normalize_integer_parameter(raw_value)
        else:
            normalized_value = _normalize_decimal_parameter(raw_value)

        if normalized_value is None:
            errors[key] = "Enter a valid positive number."
        else:
            normalized_values[key] = normalized_value

    if errors:
        return errors

    with transaction.atomic():
        for key, value in normalized_values.items():
            Parameter.objects.update_or_create(
                key=key,
                defaults={"value": value},
            )

    return {}


def _normalize_decimal_parameter(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return None

    if not amount.is_finite() or amount <= 0:
        return None

    try:
        return format(amount.quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        return None


def _normalize_integer_parameter(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return None

    if not amount.is_finite() or amount != amount.to_integral_value() or amount < 1:
        return None

    return str(int(amount))
