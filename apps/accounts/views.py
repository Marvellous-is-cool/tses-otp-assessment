from rest_framework.views import APIView, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample

from apps.accounts.serializers import *


from apps.accounts.services.otp_service import (
    request_otp, verify_otp, RateLimitExceeded, OTPLocked, OTPInvalid
)

def get_client_ip(request):
    """
    X-Forwarded-For header set by reverse proxies.
    which will be in this Format: "client, prxy1, prxy2"
    thus, we will split the forwarded for, and get the leftmost (client) IP, which is the client's very IP by using the request.META
    
    if we can't get it, we will get the "REMOTE_ADDR"
    """
    
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
    

# --- VIEWS LOGIC using drf's APIView (class)

class OTPRequestView(APIView):
    """
    We will use the "AllowAny" permission class because we want any user to request otp (for login / signin )
    """
    
    permission_classes = [AllowAny]
    
    """
    Customizing the openai schema with serializer
    """
    @extend_schema(
        summary="Request an OTP",
        description="This is a POST request that sends a 6-digit OTP to the provided email address. This is rate limited and cannot be tried for infinite time",
        request=OTPRequestSerializer,
        responses={
            202: OpenApiResponse(response=OTPRequestResponseSerializer),
            429: OpenApiResponse(response=RateLimitErrorSerializer, description="User has been Rate Limited"),
            400: OpenApiResponse(description="Invalid Input")
        },
        tags=["Authentication"]
    )
    
    def post(self, request):
        """
        POST the otp to the user's email
        
        srl = serializer
        """
        srl = OTPRequestSerializer(data=request.data)
        if not srl.is_valid():
            return Response(srl.errors, status=status.HTTP_400_BAD_REQUEST)
    
        email = srl.validated_data["email"]
        ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        
        
        try: 
            result = request_otp(email=email, ip=ip, user_agent=user_agent)
        except RateLimitExceeded as exc:
            response = Response(
                {"error":str(exc), "retry_after":exc.retry_after},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            # We will create a standard HTTP header
            response["Retry-After"] = str(exc.retry_after)
            return response
        
        return Response(result, status=status.HTTP_202_ACCEPTED) 
    

class OTPVerifyView(APIView):
    """
    We will use the "AllowAny" permission class because we want any user to request otp (for login / signin )
    """
    
    permission_classes = [AllowAny]
    
    """
    Customizing the openai schema with serializer
    """
    
    @extend_schema(
        summary="Verify OTP and get JWT tokens",
        description="This is a POST request that submits OTP, and upon success, access is granted to user and the JWT tokens are refreshed",
        request=OTPVerifySerializer,
        responses={
            200: OpenApiResponse(response=OTPVerifyResponseSerializer),
            400: OpenApiResponse(description="OTP is invalid or expired. Please try again or request a new one"),
            423: OpenApiResponse(response=LockoutErrorSerializer, description="Locked out")
        },
        tags=["Authentication"]
    )
    
    def post(self, request):
        """
        POST verify view logic
        
        srl = serializer
        """
        srl = OTPVerifySerializer(data=request.data)
        if not srl.is_valid():
            return Response(srl.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        
        email = srl.validated_data["email"]
        otp_input = srl.validated_data["otp"]
        ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        
        try:
            result = verify_otp(email=email, otp_input=otp_input, ip=ip, user_agent=user_agent)
        except OTPLocked as exc: 
            return Response(
                {"error": str(exc), "unlock_eta": exc.unlock_eta},
                status=status.HTTP_423_LOCKED
            )
        except OTPInvalid as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(result, status=status.HTTP_200_OK)
    
        
        
        


