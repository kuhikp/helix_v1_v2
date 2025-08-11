from django.shortcuts import render
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from tag_manager_component.models import TagMapper

class BearerTokenAuthentication(TokenAuthentication):
    keyword = 'Bearer'

class MigrateV1ToV2View(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_exempt)
    def post(self, request):
        
        v1_body = request.data.get('v1_body', '')
        v1_css = request.data.get('v1_css', '')
        v1_js = request.data.get('v1_js', '')

        # Use TagMapper to migrate tags from v1 to v2
        try:
            # Get all tag mappings from the database
            tag_mappings = TagMapper.objects.all()
            
            # Initialize converted content
            v2_body = v1_body
            v2_css = v1_css
            v2_js = v1_js
            
            # Apply mappings to convert v1 components to v2
            for mapping in tag_mappings:
                v2_body = v2_body.replace(mapping.v1_component_name, mapping.v2_component_name)
                v2_css = v2_css.replace(mapping.v1_component_name, mapping.v2_component_name)
                v2_js = v2_js.replace(mapping.v1_component_name, mapping.v2_component_name)
                
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
        # Remove the redundant conversion logic since we're already doing it above
        
        return Response({
            'v2_body': v2_body,
            'v2_css': v2_css,
            'v2_js': v2_js
        }, status=status.HTTP_200_OK)


def get_token_form(request):
    token = None
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user:
            token, created = Token.objects.get_or_create(user=user)
        else:
            error = 'Invalid username or password.'
    return render(request, 'api_component/get_token.html', {'token': token.key if token else None, 'error': error})
