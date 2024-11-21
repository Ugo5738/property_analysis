# from django.conf import settings
# from twilio.rest import Client


# def send_whatsapp_message(phone_number, message):
#     client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
#     client.messages.create(
#         body=message,
#         from_=f"whatsapp:+{settings.TWILIO_WHATSAPP_NUMBER}",
#         to=f"whatsapp:{phone_number}",
#     )
