from mattermostdriver import Driver
from jarbas_utils.log import LOG
import logging
import json


logging.getLogger("urllib3.connectionpool").setLevel("WARNING")
logging.getLogger("asyncio").setLevel("WARNING")
logging.getLogger("websockets.client").setLevel("WARNING")
logging.getLogger("websockets.protocol").setLevel("WARNING")


class MMostBot:
    def __init__(self, mail, pswd, url, tags=None, debug=False):
        self.debug = debug
        self.config = {"url": url,
                       "login_id": mail,
                       "password": pswd,
                       "scheme": "https",
                       "port": 443,
                       "verify": True,
                       "debug": debug}
        self.driver = Driver(self.config)
        self.tags = tags or []

    @property
    def user_id(self):
        return self.driver.users.get_user(user_id='me')["id"]

    def listen(self):
        self.driver.login()
        self.driver.init_websocket(self.event_handler)

    async def event_handler(self, event):
        event = json.loads(event)
        event_type = event.get("event", "")
        if event_type == "hello":
            self.on_connect(event)
        elif event_type == "status_change":
            self.on_status_change(event)
        elif event_type == "typing":
            self.on_typing(event)
        elif event_type == "posted":
            self.on_message(event)
        elif event_type == "channel_viewed":
            self.on_viewed(event)
        elif event_type == "preferences_changed":
            self.on_preferences_changed(event)
        elif event_type == "post_deleted":
            self.on_post_deleted(event)
        elif event_type == "user_added":
            self.on_user_added(event)
        elif event_type == "user_removed":
            self.on_user_removed(event)
        else:
            LOG.debug(event)

    def on_connect(self, event):
        LOG.info("Connected")

    def on_status_change(self, event):
        user_id = event["data"]["user_id"]
        status = event["data"]["status"]

        user_data = self.driver.users.get_user(user_id=user_id)
        username = user_data["username"]
        email = user_data["email"]

        LOG.info(username + ":" + status)

    def on_typing(self, event):
        user_id = event["data"]["user_id"]
        channel_id = event["broadcast"]["channel_id"]

        channel_data = self.driver.channels.get_channel(channel_id)
        channel_name = channel_data["name"]

        user_data = self.driver.users.get_user(user_id=user_id)
        username = user_data["username"]

        if channel_name == self.user_id + "__" + user_id:
            LOG.info(username + " is typing a direct message")
        else:
            LOG.info(username + " is typing a message in channel: " + channel_name)

    def on_message(self, event):
        post = event["data"]["post"]
        post = json.loads(post)
        sender = event["data"]["sender_name"]
        msg = post["message"]
        channel_id = post["channel_id"]
        user_id = post["user_id"]

        channel_data = self.driver.channels.get_channel(channel_id)
        channel_name = channel_data["name"]

        if channel_name == self.user_id + "__" + user_id:
            # direct_message
            if user_id != self.user_id:
                self.on_direct_message(event)
        else:
            if user_id != self.user_id:
                mention = False
                for tag in self.tags:
                    if tag in msg:
                        mention = True
                        break
                if mention:
                    self.on_mention(event)
                else:
                    LOG.info("New message at channel: " + channel_name)
                    LOG.info(sender + " said: " + msg)

    def on_mention(self, event):
        post = event["data"]["post"]
        post = json.loads(post)
        sender = event["data"]["sender_name"]
        msg = post["message"]
        channel_id = post["channel_id"]
        user_id = post["user_id"]
        channel_data = self.driver.channels.get_channel(channel_id)
        channel_name = channel_data["name"]

        for tag in self.tags:
            msg = msg.replace(tag, "")

        LOG.info("New mention at channel: " + channel_name)
        LOG.info(sender + " said: " + msg)

        self.handle_mention(msg, sender, channel_id)

    def on_user_added(self, event):
        user_id = event["data"]["user_id"]
        channel_id = event["broadcast"]["channel_id"]

        if user_id != self.user_id:
            user_data = self.driver.users.get_user(user_id=user_id)
            username = user_data["username"]
            self.send_message(channel_id, "hello @"+username)
        else:
            self.send_message(channel_id, "Blip Blop, I am a Bot!")

    def on_user_removed(self, event):
        user_id = event["broadcast"]["user_id"]
        #channel_id = event["data"]["channel_id"]
        #remover_id = event["data"]["remover_id"]

    def on_direct_message(self, event):
        post = event["data"]["post"]
        post = json.loads(post)
        sender = event["data"]["sender_name"]
        msg = post["message"]
        channel_id = post["channel_id"]

        LOG.info("Direct Message from: " + sender)
        LOG.info("Message: " + msg)
        # echo
        self.handle_direct_message(msg, sender, channel_id)

    def on_viewed(self, event):
        channel_id = event["data"]["channel_id"]
        user_id = event["broadcast"]["user_id"]

    def on_preferences_changed(self, event):
        preferences = json.loads(event["data"]["preferences"])
        for pref in preferences:
            user_id = pref["user_id"]
            category = pref["category"]
            value = pref["value"]
            LOG.debug(category + ":" + value)

    def on_post_deleted(self, event):
        msg = event["data"]["message"]

    def send_message(self, channel_id, message, file_paths=None):
        file_paths = file_paths or []
        file_ids = []
        # TODO not working
        #for f in file_paths:
        #    file_id = self.driver.files.upload_file(
        #        channel_id=channel_id,
        #        files = {'files': (f, open(f))}
        #    )['file_infos'][0]['id']
        #    file_ids.append(file_id)

        post = {
            'channel_id': channel_id,
            'message': message}
        if len(file_ids):
            post["file_ids"] = file_ids

        self.driver.posts.create_post(options=post)

    # Relevant handlers
    def handle_direct_message(self, message, sender, channel_id):
        pass

    def handle_mention(self, message, sender, channel_id):
        pass

