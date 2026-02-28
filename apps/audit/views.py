from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer
from apps.audit.filters import AuditLogFilter

class AuditLogListView(ListAPIView):
    """
    The permission is set to IsAuthenticated as only authenticated users will be able to see the log of their sessions
    """
    
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = AuditLogFilter
    
    
    # modifying the queryset to get all Audit log by filtering it by -created_at (that is, from the newest to the oldest)
    def get_queryset(self):
        return AuditLog.objects.all().order_by("-created_at")
    
    # extending the openapi(swagger) schema, creating filtering logic by setting required to false
    @extend_schema(
        summary="List audit log enteries",
        description="Paginated audit Logs. Filterable by email, event, date range. Authentication required (JWT)",
        parameters=[
            OpenApiParameter("email", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("event", str, OpenApiParameter.QUERY, required=False, enum=["OTP_REQUESTED", "OTP_VERIFIED", "OTP_FAILED", "OTP_LOCKED"]),
            OpenApiParameter("from_date", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("to_date", str, OpenApiParameter.QUERY, required=False)
        ],
        tags=["Audit"]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)