from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings

from apps.accounts.services.redis_service import (
    generate_otp, store_otp, get_otp, delete_otp, check_email_rate_limit, check_ip_rate_limit, check_failed_attempts, record_failed_attempt, clear_failed_attempts    
)

from apps.accounts.tasks import send_otp_email, write_audit_log

User = get_user_model()

# -- Exceptions (making them custom, so that we can easily know what went wrong in the view)

class RateLimitExceeded(Exception):
    def __init__(self, message, retry_after=0):
        self.retry_after = retry_after
        super().__init__(message)
        
class OTPLocked(Exception):
    def __init__(self, unlock_eta=0):
        self.unlock_eta = unlock_eta
        super().__init__("Too Many failed attempts, Account is now temporary locked")
        
class OTPInvalid(Exception):
    """We will not override the Exception class for the OTPInvalid"""
    pass

def request_otp(email, ip, user_agent):
    """
    This function grants otp to user through the user's email address, it verifies the user through the user agent meta.
    
    It first check if the user is not rate limited by his/her email/ip
    
    If not, it proceeds to send the otp to the user, and returns the ttl for the expiry (the store + expiry is done atomically)
    
    It saves this to the logger using celery for auditing purpose.
    """
    
    # [1] Firstly, we will check if the user is not rate limited
    
    #-- Check if Email is limited
    email_limited, email_retry = check_email_rate_limit(email)
    if email_limited:
        raise RateLimitExceeded(
            f"You have made too many OTP requests for this email. Please try again in {email_retry}s.",
            retry_after=email_retry
        )
        
        
    #-- Check if IP is limited
    ip_limited, ip_retry = check_ip_rate_limit(ip)
    if ip_limited:
        raise RateLimitExceeded(
            f"You have made too many OTP requests for this IP. Please try again in {ip_retry}s.",
            retry_after=ip_retry
        )
        
    # [2] If email/ip is not limited, we will generate the otp and store (atomically)
    otp = generate_otp()
    store_otp(email, otp)
    
    
    # [3] Finally, we will create an async for the create otp task which celery will handle under the hood
    send_otp_email.delay(email=email, otp=otp)
    write_audit_log.delay(
        event="OTP_REQUESTED",
        email=email,
        ip=ip,
        meta={"user_agent": user_agent}
    )
    
    # finally, we will return the expires and the success message
    return {
        "expires_in": settings.OTP_TTL_SECONDS,
        "message": "Your OTP has been sent to your email address which expires in 5 minutes"
    }
    

def verify_otp(email, otp_input, ip, user_agent):
    """
    this function takes in the otp, email and ip, and verify it over the user_agent meta for auth purposes
    
    It checks if it is locked, if not, it proceeds to find the otp, confirms if is assigned to the email and the ip
    
    if successful, it confirms and deletes the passcode - maintaining its purpose of a One Time Passcode.
    
    We write the log with celery to the Audit (whether successful, or failed (locked))
    """
    
    # [1] Firstly, we check if the otp is not locked
    is_locked, unlock_eta = check_failed_attempts(email)
    if is_locked:
        write_audit_log.delay(event="OTP", email=email, ip=ip, meta={"user_agent": user_agent, "unlock_eta": unlock_eta})
        raise OTPLocked(unlock_eta=unlock_eta)
    
    # [2] validate OTP (which means that the otp is not locked)
    stored_otp = get_otp(email)
    if stored_otp is None or stored_otp != otp_input:
        failed_count, unlock_eta = record_failed_attempt(email)
        write_audit_log.delay(
            event="OTP_FAILED", email=email, ip=ip, meta={"user_agent": user_agent, "failed_count": failed_count, "reason": "expired" if stored_otp is None else "invalid"},
        )
        
        if failed_count >= settings.RATE_LIMIT["FAILED_MAX"]:
            raise OTPLocked(unlock_eta=unlock_eta)
        raise OTPInvalid(
            f"Your entered OTP is Invalid or expired. Please try again or request a new OTP."
            f"{settings.RATE_LIMIT["FAILED_MAX"] - failed_count} attempts(s) remaining."
        )
        
    # [3] Since we have handled the validation, the OTP will be valid if it did not hit any of the validation, thus, we can delete and clear failed attempts
    delete_otp(email) 
    clear_failed_attempts(email)
    
    
    # [4] Atomic creation of User (using Django's ORM get_or_create ) - either get a user (login) or create a user (signin) upon valid otp
    user, created = User.objects.get_or_create(
        email=email,
        defaults={"username": email}
    )
    
    # [5] Refresh token for user to access audit log and write audit log 
    
    refresh = RefreshToken.for_user(user)
    write_audit_log.delay(event="OTP_VERIFIED", email=email, ip=ip, meta={"user_agent": user_agent, "user_created": created})
    
    # [6] Finally, return the access, refresh and created at
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "created": created
    } 
    
    

        
