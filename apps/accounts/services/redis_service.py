import secrets
import string
from django.core.cache import cache
from django.conf import settings

def get_redis_client():
    from django_redis import get_redis_connection
    return get_redis_connection("default")

# -- centralized Key naming schema (to help across the codebase) -- 

"""
Since redis is a flat key-value store, we will use : as the naming convention to stimulate namespacing (e.g otp:value:user@email.com) - which also makes it readable.
"""

def _otp_key(email):
    return f"otp:value:{email.lower()}"

def _otp_email_rate_key(email):
    return f"rate:otp_req:email:{email.lower()}"

def _otp_ip_rate_key(ip):
    return f"rate:otp_req:ip:{ip}"

def _otp_failed_key(email):
    return f"rate:otp_fail:{email.lower()}"


# --- OTP Generation Logic ---

def generate_otp(length=6):
    """
    I used Secret module (which uses the os's cryptography secure random number generator ) over random to avoid predictability.
    """
    
    return "".join(secrets.choice(string.digits) for _ in range(length))

def store_otp(email, otp):
    """
    We get the redis client, and then we do an atomic operation of set key and expiry (i.e., if set failed, expiry will not bother to proceed, and if set failed and expiry did not work, set will be cancelled)
    
    setex -> (key, ttl_seconds, value) 
    the ttl_seconds is set in config.settings
    """
    
    client = get_redis_client()
    client.setex(_otp_key(email), settings.OTP_TTL_SECONDS, otp)
    
def get_otp(email):
    """
    We simply get the code (value) for the email address of the user as defined above
    """
    client = get_redis_client()
    value = client.get(_otp_key(email))
    
    # we will get bytes from redis, thus we decode to string "123456", None if code doesn't exist as error handling
    return value.decode() if value else None

def delete_otp(email):
    """
    Delete otp upon successful verification, this enforces one time usage.
    """
    client = get_redis_client()
    client.delete(_otp_key(email))
    

# --- LUA SCRIPT  --- 


"""
-- WHY LUA SCRIPT HERE?

#-- THE ISSUE
We make use of two redis commands:
incr and expire which is called by client:

i.e.,   client.incr(key)            - 1
        client.expire(key, ttl)     - 2
        
Between this two commands, the user might fiddle or maybe a server may send a request between these two commands, which will affect them (if the server crashes between any of them, the key will not get the ttl, thus, our user will be blocked)

#-- WHERE LUA COMES IN
Thus, to solve this, we will make use of Lua for Isolation (thus we will treat it as ACID operation), Lua will run Atomically; since redis is single-threaded (run a task one after the other), while the Lua Script runs, nothing else executes and by that, we are able to make Redis work like a database on ACID operation.

While there are other methods like MULTI/EXEC, Lua is more robust and a preferred solution approach
"""

# --- START OF LUA SCRIPT
_INCR_WITH_TTL_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""
# --- END OF LUA SCRIPT

# --- Cont. of Atomic Operations
def _atomic_increment(key, windows_seconds):
    """
    Using Atomic Operation, we sets TTL only on first increment.
    which returns (count, ttl_remaining)
    
    We will call the Lua Script with the register_script()
    """
    client = get_redis_client()
    script = client.register_script(_INCR_WITH_TTL_SCRIPT)
    count = script(keys=[key], args=[windows_seconds])
    ttl = client.ttl(key)
    return int(count), int(ttl)

def check_email_rate_limit(email):
    """
    We check if the user's email is above the rate limit (rl["EMAIL_MAX"]) which returns the;
        (is_limited: bool (true/false), retry_after: int (the number of minutes to retry after being rate limited))
    """
    rl = settings.RATE_LIMIT
    count, ttl = _atomic_increment(_otp_email_rate_key(email), rl["EMAIL_WINDOW"])
    if count > rl["EMAIL_MAX"]:
        return True, max(ttl, 0)
    return False, 0

def check_ip_rate_limit(ip):
    """
    We check if the user's ip is above the rate limit (rl["IP_MAX"]) which returns the;
        (is_limited: bool (true/false), retry_after: int (the number of minutes to retry after being rate limited))
    """
    
    rl = settings.RATE_LIMIT
    count, ttl = _atomic_increment(_otp_ip_rate_key(ip), rl["IP_WINDOW"])
    if count > rl["IP_MAX"]:
        return True, max(ttl, 0)
    return False, 0

def check_failed_attempts(email):
    """
    This check the failed attempts 
    CHECK-ONLY
    which returns;
        (is_locked: bool, unlock_eta: int)
    """
    rl = settings.RATE_LIMIT
    client = get_redis_client()
    raw = client.get(_otp_failed_key(email))
    if raw is None:
        return False, 0
    count = int(raw)
    if count >= rl["FAILED_MAX"]:
        ttl = client.ttl(_otp_failed_key(email))
        return True, max(ttl, 0)
    return False, 0

def record_failed_attempt(email):
    """
    This records failed attempt atomically
    INCREMENT
    which returns;
        (count, unlock_eta)
    """
    rl = settings.RATE_LIMIT
    count, ttl = _atomic_increment(_otp_failed_key(email), rl["FAILED_WINDOW"])
    return count, max(ttl, 0) 

def clear_failed_attempts(email):
    """
    To close on successful verification, which resets teh counter
    """
    client = get_redis_client()
    client.delete(_otp_failed_key(email))   