from mattermost_bridge import JarbasMattermostBridge, platform
from jarbas_hive_mind import HiveMindConnection


def connect_mattermost_to_hivemind(mail, pswd, url, tags=None,
                                   host="127.0.0.1",
                                   crypto_key=None,
                                   port=5678, name="JarbasMattermostBridge",
                                   key="unsafe", useragent=platform):
    con = HiveMindConnection(host, port)

    terminal = JarbasMattermostBridge(mail=mail,
                                      pswd=pswd,
                                      url=url,
                                      tags=tags,
                                      crypto_key=crypto_key,
                                      headers=con.get_headers(name, key),
                                      useragent=useragent)

    con.secure_connect(terminal)


if __name__ == '__main__':
    # TODO argparse
    url = "chat.mycroft.ai"
    mail = "xxx"
    pswd = "xxx"
    tags = ["@bot"]
    connect_mattermost_to_hivemind(mail, pswd, url, tags)
