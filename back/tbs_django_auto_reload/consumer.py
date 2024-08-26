from channels.generic.websocket import AsyncWebsocketConsumer


class ReloadConsumer(AsyncWebsocketConsumer):
    async def connect(self, **kwargs):
        # everybody joins the same channel!
        await self.channel_layer.group_add("reload", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("reload", self.channel_name)

    async def reload(self, event):
        await self.send(text_data="reload")
