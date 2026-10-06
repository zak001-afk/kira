from pathlib import Path
import ast

p = Path("kira_ui.py")
text = p.read_text(encoding="utf-8")
bad = '''        if last_error is not None:
            self._json_error(503, "KIRA backend unavailable. Start the KIRA desktop app or web launcher.")
            return
        finally:
            connection.close()
        self._send_payload(status, content_type, payload)
        self.send_response(status)
'''
good = '''        if last_error is not None:
            self._json_error(503, "KIRA backend unavailable. Start the KIRA desktop app ou web launcher.")
            return
        self.send_response(status)
'''
if bad in text:
    p.write_text(text.replace(bad, good), encoding="utf-8")
    print("kira_ui.py corrigé")
else:
    print("bloc introuvable (deja corrige ?)")

ast.parse(p.read_text(encoding="utf-8"))
print("syntaxe OK")