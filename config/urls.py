from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("silk/", include("silk.urls", namespace="silk")), 
    
    # OpenAPI schema (will download the schema upon click)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    
    # Interactive Swagger UI
    path("api/schema/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/audit/", include("apps.audit.urls")), 
]