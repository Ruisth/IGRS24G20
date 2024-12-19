import KSR as KSR

def mod_init():
    KSR.info("===== PBX2.0 Service Initialized =====\n")
    return PBX20Service()

class PBX20Service:
    def __init__(self):
        KSR.info("===== PBX20Service.__init__ =====\n")

    def child_init(self, rank):
        KSR.info(f"===== PBX20Service.child_init(rank={rank}) =====\n")
        return 0

    def ksr_request_route(self, msg):
        if msg.Method == "REGISTER":
            return self.handle_register(msg)
        elif msg.Method == "INVITE":
            return self.handle_invite(msg)
        elif msg.Method == "MESSAGE":
            return self.handle_message(msg)
        elif msg.Method in ["ACK", "CANCEL", "BYE"]:
            return self.handle_other_methods(msg)
        else:
            KSR.info(f"Unhandled SIP method: {msg.Method}\n")
            return 1

    def handle_register(self, msg):
        domain = KSR.pv.get("$td")
        if domain != "acme.pt":
            KSR.info("Rejected registration for invalid domain.\n")
            KSR.sl.send_reply(403, "Forbidden")
            return 1

        KSR.info(f"Registering user: {KSR.pv.get('$tu')}\n")
        KSR.registrar.save("location", 0)
        return 1

    def handle_invite(self, msg):
        domain = KSR.pv.get("$td")
        if domain != "acme.pt":
            KSR.info("Rejected INVITE for invalid domain.\n")
            KSR.sl.send_reply(403, "Forbidden")
            return 1

        if not KSR.registrar.lookup("location"):
            KSR.info("User not registered. Sending 404.\n")
            KSR.sl.send_reply(404, "Not Found")
            return 1

        dst_uri = KSR.pv.get("$ru")
        busy_state = KSR.dialog.dlg_bye_reason()

        if busy_state == "Busy":
            ad_uri = "sip:busyann@127.0.0.1:5080"
            KSR.info(f"User busy. Forwarding to announcement server at {ad_uri}\n")
            KSR.pv.seti("$du", ad_uri)
            KSR.tm.t_relay()
            return 1
        elif busy_state == "Conference":
            ad_uri = "sip:inconference@127.0.0.1:5080"
            KSR.info(f"User in conference. Forwarding to announcement server at {ad_uri}\n")
            KSR.pv.seti("$du", ad_uri)
            KSR.tm.t_relay()
            return 1

        KSR.info("Forwarding INVITE to registered user.\n")
        KSR.tm.t_relay()
        return 1

    def handle_message(self, msg):
        uri = KSR.pv.get("$ru")
        if uri == "sip:validar@acme.pt":
            self.validate_pin(msg)
        elif KSR.pv.get("$fu") == "sip:gestor@acme.pt" and KSR.pv.get("$rb").strip().lower() == "report":
            self.send_kpi_report()
        else:
            KSR.info("Unhandled MESSAGE URI.\n")
        return 1

    def validate_pin(self, msg):
        body = KSR.pv.get("$rb")
        if body.strip() == "0000":
            KSR.info("PIN validation successful.\n")
            KSR.sl.send_reply(200, "OK")
        else:
            KSR.info("PIN validation failed.\n")
            KSR.sl.send_reply(403, "Forbidden")

    def send_kpi_report(self):
        report_content = "Chamadas atendidas: 10\nConferências realizadas: 5"
        KSR.info("Sending KPI report.\n")
        KSR.textops.text_reply_with_body(200, "OK", report_content)

    def handle_other_methods(self, msg):
        KSR.info(f"Handling method: {msg.Method}\n")
        KSR.tm.t_relay()
        return 1

    def ksr_reply_route(self, msg):
        KSR.info("===== PBX20Service.reply_route =====\n")
        return 1

    def ksr_onsend_route(self, msg):
        KSR.info("===== PBX20Service.onsend_route =====\n")
        return 1

    def ksr_onreply_route_INVITE(self, msg):
        KSR.info("===== PBX20Service.onreply_route_INVITE =====\n")
        return 0

    def ksr_failure_route_INVITE(self, msg):
        KSR.info("===== PBX20Service.failure_route_INVITE =====\n")
        return 1
