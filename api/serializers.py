from rest_framework import serializers


class AccountSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='pk')
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    is_superuser = serializers.BooleanField()
