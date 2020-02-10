from mattermost_bridge.mmost import MMostBot

url = "chat.mycroft.ai"
mail = ""
pswd = ""


class EchoBot(MMostBot):
    def handle_direct_message(self, message, sender, channel_id):
        self.send_message(channel_id, message)

    def handle_mention(self, message, sender, channel_id):
        message = "@" + sender + " " + message
        self.send_message(channel_id, message)


bot = MMostBot(mail, pswd, url, tags=["@bot"])
bot.listen()
