from django.db import models

class AuditLog(models.Model):
    class Event(models.TextChoices):
        """
        Creating text choices that creates enum, which helps in validation (for django (db validation), serializer and the swagger)
        
        db_index=True will help in indexing to make the queries run fast.
        """
        
        OTP_REQUESTED = "OTP_REQUESTED", "OTP_Requested"
        OTP_VERIFIED = "OTP_VERIFIED", "OTP_Verified"
        OTP_FAILED = "OTP_FAILED", "OTP_Failed"
        OTP_LOCKED = "OTP_LOCKED", "OTP_Locked"
        
    event = models.CharField(max_length=32, choices=Event.choices, db_index=True)
    email = models.EmailField(db_index=True)
    ip_address = models.GenericIPAddressField(protocol="both", unpack_ipv4=True, null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
        
    class Meta:
        ordering = ["created_at"]
            
    def __str__(self):
        return f"[- {self.event} -] {self.email} @ {self.created_at}"