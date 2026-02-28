from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="accounts.send_otp_email")
def send_otp_email(self, email, otp):
    """
    we are binding so that the task will have access to the task instance (self).
    By this, we can get to call self.retry() incase something fails
    
    This task logs the otp sent to the email
    """
    try: 
        logger.info(
            "\n" + "=" * 50 + "\n"
            f" >>> OTP EMAIL TO: {email} "
            f" <<< CODE: {otp}\n"
            f" >>> (expires in 5 minutes)\n"
            + "=" * 50
        )
    except Exception as exc:
        raise self.retry(exc=exc)
    

@shared_task(bind=True, max_retries=5, default_retry_delay=30, name="accounts.write_audit_log")
def write_audit_log(self, event, email, ip, meta=None):
    """
    wW are binding so that the task will have access to the task instance (self).
    By this, we can get to call self.retry() incase something fails
    
    This task logs audit, and audit is imported inside the try to avoid circular imports, because of Django initialization.
    """
    try:
        from apps.audit.models import AuditLog
        AuditLog.objects.create(
            event=event,
            email=email,
            ip_address=ip,
            metadata=meta or {}
        )
        logger.info(f"[:::] Audit: [{event}] {email} from {ip} ")
    except Exception as exc: 
        raise self.retry(exc=exc)