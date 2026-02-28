import django_filters
from apps.audit.models import AuditLog

class AuditLogFilter(django_filters.FilterSet):
    email = django_filters.CharFilter(field_name="email", lookup_expr="iexact")
    event = django_filters.ChoiceFilter(field_name="event", choices=AuditLog.Event.choices)
    
    # 'from' is a reserved word in python, thus, I made use of 'from_date' and 'to_date' (but teh fields are override in the Meta)
    
    from_date = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    to_date = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    
    class Meta:
        model = AuditLog
        fields = ["email", "event", "from_date", "to_date"]