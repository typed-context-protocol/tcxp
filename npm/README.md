# tcxp (npm)

The Typed Context Protocol for JavaScript and Node:

- **A JavaScript address parser** with the same canonical form as the Python library
  (both pass the shared `vectors.json`).
- **The `tcxp` command.** It runs the Python library bundled in this package
  (installed once into `~/.tcxp/venv`; needs Python 3.10+, no network).
- **A local server**: the animated docs at `/` and the CLI as JSON at `/api/<command>`.

```bash
npx tcxp demo            # the Section 41 demo in your terminal
npx tcxp roll            # replay it as a context roll
npx tcxp fleet           # 10,000 Observatrons, with and without typed context
npx tcxp docs            # open the animated docs
npx tcxp serve           # http://127.0.0.1:8765/api/fleet?observatrons=1000&epochs=6
npm install -g tcxp      # then just: tcxp …
```

```js
import { Address, URI } from "tcxp";

const a = Address.parse("!tcxp:/reason?tax_year=&task=section_41");
a.with({ tax_year: 2024 }).toString();   // "!tcxp:/reason?task=section_41&tax_year=2024"
a.toURI();                                // "tcxp:/reason?task=section_41&tax_year=" (valid-URI spelling)

import { createTcxpServer } from "tcxp/server";
createTcxpServer().listen(8765, "127.0.0.1");
```

The server binds to 127.0.0.1, runs only allow-listed commands and flags, never uses a
shell, and does not expose anything that spends money (`--real`) or touches files.

`tcxp setup` installs the Python side now; `tcxp where` shows where; `tcxp uninstall`
removes it. Set `TCXP_PYTHON` to choose the interpreter and `TCXP_HOME` to move `~/.tcxp`.

`npm test` checks conformance; `npm run test:server` checks the server.

Licensed under the W3C Software and Document License (W3C-20150513).
