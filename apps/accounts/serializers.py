from rest_framework import serializers

class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="Enter the Email address to send the OTP to")
    
    # validate email (using the drf's validate_ logic) by normalizing and striping unwanted parts like extra spaces, etc
    def validate_email(self, value):
        return value.lower().strip()
    
    
class OTPRequestResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    expires_in = serializers.IntegerField(help_text="Seconds until OTP expires")
    
class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    
    def validate_email(self, value):
        return value.lower().strip()
    
    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must only contain digits")
        return value
    
class OTPVerifyResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    created = serializers.BooleanField()
    

class RateLimitErrorSerializer(serializers.Serializer): 
    error = serializers.CharField()
    retry_after = serializers.IntegerField()        


class LockoutErrorSerializer(serializers.Serializer): 
    error = serializers.CharField()
    unlock_eta = serializers.IntegerField()        
    
    
    