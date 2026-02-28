from rest_framework import serializers
from apps.audit.models import AuditLog

class AuditLogSerializer(serializers.ModelSerializer):
    """
    The event is made to be readonly since we are auditing it and we also don't want to tamper with the data
    """
    event_display = serializers.CharField(source="get_event_display", read_only=True)
    
    class Meta:
        model = AuditLog
        fields = ["id", "event", "event_display", "email", "ip_address", "user_agent", "metadata", "created_at"]
        read_only_fields = fields