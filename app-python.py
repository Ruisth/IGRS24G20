import KSR as KSR
import threading
from concurrent.futures import ThreadPoolExecutor

# Controlador para evitar loops de INVITE
class CallTracker:
    def __init__(self):
        self.processed_calls = set()

    def track_call(self, call_id):
        if call_id in self.processed_calls:
            return True  # Já foi processada antes
        else:
            self.processed_calls.add(call_id)
            return False

    def reset(self):
        self.processed_calls.clear()

call_tracker = CallTracker()

def mod_init():
    KSR.info("===== PBX20Service Initialized with Advanced Call Forwarding =====\n")
    return PBX20Service()

class PBX20Service:
    def __init__(self):
        KSR.info("===== PBX20Service.__init__ =====\n")
        self.kpis = {
            "calls_auto_attended": 0,
            "conferences_created": 0,
        }

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

        contact = KSR.pv.get("$ct")
        expires = KSR.pv.get("$hdr(Expires)")

        if contact == "*" or (expires and int(expires) == 0):
            KSR.info(f"Deregistering user: {KSR.pv.get('$tu')}\n")
            if not KSR.registrar.save("location", 0):
                KSR.info("User not registered. Sending 404.\n")
                KSR.sl.send_reply(404, "Not Found")
            else:
                KSR.sl.send_reply(200, "OK")
            return 1

        KSR.info(f"Registering user: {KSR.pv.get('$tu')}\n")
        KSR.registrar.save("location", 1)  # Register user with location data
        return 1

    def handle_invite(self, msg):
        # Adicionar controle de loop usando Call-ID
        call_id = KSR.pv.get("$ci")
        if call_tracker.track_call(call_id):
            KSR.info(f"Call {call_id} already processed, discarding.\n")
            return -1  # Descarta a mensagem, evita loop

        from_domain = KSR.pv.get("$fd")
        to_domain = KSR.pv.get("$td")

        if from_domain != "acme.pt":
            KSR.info("Rejected INVITE for non-ACME originating domain.\n")
            KSR.sl.send_reply(403, "Forbidden")
            return 1

        if to_domain != "acme.pt":
            KSR.info("Rejected INVITE for non-ACME destination domain.\n")
            KSR.sl.send_reply(403, "Forbidden")
            return 1

        # Redirecionamento para sala de conferência
        uri = KSR.pv.get("$ru")
        if uri == "sip:conferencia@acme.pt":
            KSR.info("Redirecting to conference room.\n")
            
            # Modifica a URI de destino
            KSR.pv.sets("$ru", "sip:conferencia@127.0.0.1:5090")
            KSR.tm.t_relay()

            self.kpis["conferences_created"] += 1
            return 1

        # Verifica registro
        if not KSR.registrar.lookup("location"):
            KSR.info("User not registered. Sending 404.\n")
            KSR.sl.send_reply(404, "Not Found")
            return 1

        user_status = self.get_user_status()

        if user_status == "busy":
            self.proxy_to_announcement("sip:busyann@127.0.0.1:5080", msg)
            return 1

        elif user_status == "in_conference":
            self.proxy_to_announcement("sip:inconference@127.0.0.1:5080", msg, is_conference=True)
            return 1

        KSR.info("Forwarding INVITE to registered user.\n")
        KSR.tm.t_relay()  # Encaminha o INVITE normalmente

        self.kpis["calls_auto_attended"] += 1
        return 1

    def handle_message(self, msg):
        uri = KSR.pv.get("$ru")
        if uri == "sip:validar@acme.pt":
            self.validate_pin(msg)
        elif KSR.pv.get("$fU") == "gestor" and "Report" in KSR.pv.get("$rb"):
            self.report_kpis(msg)
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

    def report_kpis(self, msg):
        report = f"KPIs:\n" \
                 f" - Calls Auto-Attended: {self.kpis['calls_auto_attended']}\n" \
                 f" - Conferences Created: {self.kpis['conferences_created']}\n"
        KSR.msg.send(msg.SrcURI, report)

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

    def proxy_to_announcement(self, server_uri, msg, is_conference=False):
        """
        Proxy the request to the appropriate announcement server.
        :param server_uri: The URI of the announcement server
        :param msg: The SIP message being processed
        :param is_conference: If True, handle additional conference logic
        """
        try:
            KSR.info(f"Proxying to announcement server: {server_uri}\n")
            KSR.tm.t_relay_to_uri(server_uri)
            if is_conference:
                KSR.info("Handling DTMF logic for conference redirection.\n")
                if self.detect_dtmf(msg) == "0":
                    KSR.info("DTMF '0' detected. Joining conference.\n")
                    KSR.tm.t_relay_to_uri("sip:conferencia@127.0.0.1:5090")
            return True
        except Exception as e:
            KSR.err(f"Error during proxying to announcement server: {str(e)}\n")
            KSR.sl.send_reply(500, "Internal Server Error")
        return False

    def get_user_status(self):
        # Mock implementation. Replace with actual logic to check user's status.
        return "available"

    def detect_dtmf(self, msg):
        # Mock implementation to detect DTMF tones. Replace with actual SIP event handling.
        return "0"
