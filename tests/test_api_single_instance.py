"""One KIRA engine per port: the API server refuses to double-bind.

Regression 2026-09-29: the single-threaded HTTPServer blocked on slow tool
calls, a second KIRA launch then bound the SAME port on Windows, and the two
processes split the truth (approvals ran in one, /api/agents answered from
the other with an empty feed). The server is now threaded AND refuses to
start when the port is already served.
"""
import socket
import unittest

import kira_api


class SingleInstanceTests(unittest.TestCase):
    def test_server_is_threaded(self):
        # A blocked handler must never freeze the other requests again.
        server = kira_api.start_server(host="127.0.0.1", port=0, daemon=True)
        self.addCleanup(server.shutdown)
        self.assertIs(server.__class__, kira_api.ThreadingHTTPServer)
        self.assertTrue(server.daemon_threads)

    def test_second_server_on_a_live_port_is_refused(self):
        first = kira_api.start_server(host="127.0.0.1", port=0, daemon=True)
        self.addCleanup(first.shutdown)
        port = first.server_address[1]
        with self.assertRaises(OSError) as caught:
            kira_api.start_server(host="127.0.0.1", port=port, daemon=True)
        self.assertIn("already served", str(caught.exception))

    def test_probe_answers_when_a_live_server_runs(self):
        first = kira_api.start_server(host="127.0.0.1", port=0, daemon=True)
        self.addCleanup(first.shutdown)
        port = first.server_address[1]
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.settimeout(2.0)
            self.assertEqual(probe.connect_ex(("127.0.0.1", port)), 0)
        finally:
            probe.close()


if __name__ == "__main__":
    unittest.main()
