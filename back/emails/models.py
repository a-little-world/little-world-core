from django.db import models
from rest_framework import serializers
from management.models.user import User


class EmailLog(models.Model):
    # We set on_delete SET_NULL so these logges are not deleted when a user is deleted and vice verca
    sender = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='sender')
    receiver = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='receiver')

    # The time of this log creation, should be roughly equivaent to send time
    time = models.DateTimeField(auto_now_add=True)

    template = models.CharField(max_length=255, blank=True)

    # This marks wheather or not the code to send the email as trown an error
    sucess = models.BooleanField(default=False)

    # hash as wike like to have everywhere :)

    # For this we always expect:
    # template: '...html', email_rendered_html: '...html_str', kwargs: kwargs for creating the mail
    data = models.JSONField()

class AdvancedEmailLogSerializer(serializers.ModelSerializer):

    class Meta:
        model = EmailLog
        fields = '__all__'
        
    def to_representation(self, instance):
        from management.models.profile import MinimalProfileSerializer
        from emails.mails import get_mail_data_by_name, encode_mail_params

        representation =  super().to_representation(instance)
        
        # TODO: using the whole profile serializer here is a bit expensive!
        representation['sender'] = {
            'id': instance.sender.pk,
            'hash': instance.sender.hash,
            'email': instance.sender.email,
            'profile': MinimalProfileSerializer(instance.sender.profile).data
        }
        
        representation['receiver'] = {
            'id': instance.receiver.pk,
            'hash': instance.receiver.hash,
            'email': instance.receiver.email,
            'profile': MinimalProfileSerializer(instance.receiver.profile).data
        }

        email_params = instance.data["params"]
        template_name = instance.template
        print("Template: " + str(template_name), email_params)
        mail_meta = get_mail_data_by_name(template_name)
        encoded_mail_data = encode_mail_params(email_params)
        
        url = f"/emails/{template_name}/{encoded_mail_data}"
        representation['retrieve'] = url

        return representation

class EmailLogSerializer(serializers.ModelSerializer):

    class Meta:
        model = EmailLog
        fields = '__all__'
