import json
import logging
import os
import sys
import threading
from uuid import uuid4

# import easygui
import requests
import urllib3
from flask import Flask, render_template, request
from push_receiver import PushReceiver
from push_receiver.android_fcm_register import AndroidFCM
from sys import platform
import webbrowser

# Dealing with hiding the messages :)
cli = sys.modules["flask.cli"]
cli.show_server_banner = lambda *x: None

flask_logger = logging.getLogger("werkzeug")
flask_logger.setLevel(logging.ERROR)

push_receiver_logger = logging.getLogger("push_receiver")
push_receiver_logger.setLevel(logging.ERROR)

API_KEY = "AIzaSyB5y2y-Tzqb4-I4Qnlsh_9naYv_TD8pCvY"
PROJECT_ID = "rust-companion-app"
GCM_SENDER_ID = "976529667804"
GMS_APP_ID = "1:976529667804:android:d6f1ddeb4403b338fea619"
ANDROID_PACKAGE_NAME = "com.facepunch.rust.companion"
ANDROID_PACKAGE_CERT = "E28D05345FB78A7A1A63D70F4A302DBF426CA5AD"

def get_config_file():
    return (
        f"{str(os.path.dirname(os.path.realpath(__file__)))}{os.sep}rustplus.py.config.json"
    )


class RustCli:
    def __init__(self) -> None:
        self.token = ""
        self.uuid = uuid4()
        self.chrome_path = ""

    @staticmethod
    def get_user_data_directory():
        if(platform == "darwin"):
            return str(os.path.dirname(os.path.realpath(__file__))) + "/ChromeData"
        else:
            return str(os.path.dirname(os.path.realpath(__file__))) + "\\ChromeData"

    @staticmethod
    def read_config(file):
        try:
            with open(file) as fp:
                return json.load(fp)
        except Exception:
            return {}

    @staticmethod
    def update_config(file, data):
        with open(file, "w") as outputFile:
            json.dump(data, outputFile, indent=4, sort_keys=True)

    def get_expo_push_token(self, token):

        response = requests.post(
            "https://exp.host/--/api/v2/push/getExpoPushToken",
            data={
                "deviceId": uuid4(),
                "projectId": "49451aca-a822-41e6-ad59-955718d0ff9c",
                "appId": "com.facepunch.rust.companion",
                "deviceToken": token,
                "type": "fcm",
                "development": False,
            },
        )

        return response.json()["data"]["expoPushToken"]

    def register_with_rust_plus(self, auth_token, expo_push_token):

        encoded_body = json.dumps(
            {
                "AuthToken": auth_token,
                "DeviceId": "rustplus.py",
                "PushKind": 3,
                "PushToken": expo_push_token,
            }
        ).encode("utf-8")

        return urllib3.PoolManager().request(
            "POST",
            "https://companion-rust.facepunch.com:443/api/push/register",
            headers={"Content-Type": "application/json"},
            body=encoded_body,
        )

    def client_view(self):
        if(self.chrome_path == None or self.chrome_path == ""):
            print("woof2")
            if(platform == "linux"):
                self.chrome_path = "/usr/bin/google-chrome-stable"
            elif(platform == "darwin"):
                self.chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
            elif(platform == "win32"):
                self.chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            else:
                print("We are not sure where Google Chrome is installed. Please add the path to the rustplus.py.config.json which is in the current directory under variable chrome_path. Thanks!")
                exit(-1)

        webbrowser.register('chrome', None,webbrowser.BackgroundBrowser(self.chrome_path))
        web = webbrowser.get('chrome')

        web.args.append("--incognito")
        web.args.append("--disable-web-security")
        web.args.append("--disable-popup-blocking")
        web.args.append("--disable-site-isolation-trials")
        web.args.append("--user-data-dir="+ self.get_user_data_directory())
        print(web.args)
        web.open_new_tab("http://localhost:3000")
        #os.system(
        #    self.chrome_path+" --incognito http://localhost:3000 --disable-web-security --disable-popup-blocking --disable-site-isolation-trials 
        #    )


    def link_steam_with_rust_plus(self):

        thread = threading.Thread(target=self.client_view)
        thread.start()

        app = Flask(__name__)

        @app.route("/")
        def main():
            return render_template("pair.html")

        @app.route("/callback")
        def callback():
            self.token = request.args["token"]
            try:
                request.environ.get("werkzeug.server.shutdown")()
            except:
                pass

            return "All Done!"

        app.run(port=3000)

        return self.token

    def fcm_register(self):

        try:
            with open(get_config_file(), "r") as file:
                self.chrome_path = json.load(file)["chrome_path"]
        except FileNotFoundError:
            self.chrome_path = None

        print("Registering with FCM")
        fcm_credentials = AndroidFCM.register(API_KEY, PROJECT_ID, GCM_SENDER_ID, GMS_APP_ID, ANDROID_PACKAGE_NAME,
                                              ANDROID_PACKAGE_CERT)

        print("Registered with FCM")

        print("Fetching Expo Push Token")

        expo_push_token = None

        try:
            expo_push_token = self.get_expo_push_token(fcm_credentials["fcm"]["token"])
        except Exception:
            print("Failed to fetch Expo Push Token")
            quit()

        # show expo push token to user
        print("Successfully fetched Expo Push Token")
        print("Expo Push Token: " + expo_push_token)

        # tell user to link steam with rust+ through Google Chrome
        print(
            "Google Chrome is launching so you can link your Steam account with Rust+"
        )
        rustplus_auth_token = self.link_steam_with_rust_plus()

        # show rust+ auth token to user
        print("Successfully linked Steam account with Rust+")
        print("Rust+ AuthToken: " + rustplus_auth_token)

        print("Registering with Rust Companion API")
        try:
            self.register_with_rust_plus(rustplus_auth_token, expo_push_token)
        except Exception:
            print("Failed to register with Rust Companion API")
            quit()
        print("Successfully registered with Rust Companion API.")

        # save to config
        config_file = get_config_file()
        self.update_config(
            config_file,
            {
                "fcm_credentials": fcm_credentials,
                "expo_push_token": expo_push_token,
                "rustplus_auth_token": rustplus_auth_token,
                "chrome_path": self.chrome_path,
            },
        )

        print("FCM, Expo and Rust+ auth tokens have been saved to " + config_file)

    def on_notification(self, obj, notification, data_message):

        print(
            json.dumps(
                json.loads(notification["data"]["body"]), indent=4, sort_keys=True
            )
        )

    def fcm_listen(self):

        try:
            with open(get_config_file(), "r") as file:
                credentials = json.load(file)
        except FileNotFoundError:
            print("Config File doesn't exist! Run 'register' first")
            quit()

        print("Listening...")

        PushReceiver(credentials["fcm_credentials"]).listen(callback=self.on_notification)


if __name__ == "__main__":

    cli = RustCli()

    if len(sys.argv) >= 2:
        if sys.argv[1] == "register":
            cli.fcm_register()
        elif sys.argv[1] == "listen":
            cli.fcm_listen()

    else:
        cli.fcm_register()
        cli.fcm_listen()
