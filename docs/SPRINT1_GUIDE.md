# Sprint 1 guide: running and demonstrating AfterLife

This guide covers the Sprint-1 build: what is in it, how to run it on a Windows
laptop, how to demonstrate it, and how to deploy it.

## 1. What Sprint 1 delivers

| User story | Where to see it |
|---|---|
| Run an instant scan in the browser after giving consent | *Scan & Assess* → **Scan your device** |
| Add device type, age and any fault the browser cannot see | The **Complete the picture** form |
| See a combined score and grade with every adjustment explained | **Combined score** card and waterfall |
| Get an end-of-life risk from a model trained on real repair outcomes | Passport card, **Lifecycle outlook** bars |
| See remaining safe years and the lifecycle stage | **Safe service life** and **Lifecycle pipeline** cards |
| Get a keep / repair / sell / recycle recommendation | **Lifecycle pathways** card |
| See the carbon cost of buying a replacement on this grid | **Would replacing it be greener?** card |
| Receive a signed, tamper-proof passport with a QR code | Passport card → **Save passport (JSON)** / **Save QR (PNG)** |
| Check that a passport is genuine | *Passport Verifier* page |
| See the evidence and datasets behind every number | *The Argument*, *Our Research*, *Data Sources* |

## 2. One-time setup

You need **Python 3.12**, **Node.js 20 or newer**, and **Git**.

Open **Command Prompt** (not PowerShell, which can block `npm`) in the project
folder and run:

```bat
py -3.12 -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

This takes a few minutes the first time. You never need to repeat it unless
`requirements.txt` or `frontend/package.json` changes.

## 3. Running it (two terminals)

In VS Code: **Terminal → New Terminal**, then use the **˅** arrow next to **+**
to pick **Command Prompt**. Open two of them.

**Terminal 1: backend**

```bat
cd path\to\AfterLife
set PYTHONPATH=.
venv\Scripts\python -m uvicorn api.main:app --port 8000
```

Wait for `Application startup complete.`

**Terminal 2: frontend**

```bat
cd path\to\AfterLife\frontend
npm run dev
```

Open **http://localhost:5173** in Chrome or Edge.
The API's own documentation page is at **http://localhost:8000/docs**.

To stop either one, click in its terminal and press **Ctrl+C**.

## 4. Demo script (about 3 minutes)

1. **Home page.** The headline finding and the three dataset counts underneath
   are read live from the data, not typed in.
2. **Scan your device → Allow & scan.** Point out the consent list: no files, no
   browsing history, no personal data.
3. **Complete the picture.** Pick the device type, enter an age, optionally type
   a fault (for example "battery drains fast"), then **Assess & mint passport**.
4. **Passport (left).** It is signed, and the ML outlook is *inside* the
   signature, so it cannot be edited either.
5. **Assessment (right).** Walk through the score waterfall, the years left, the
   pathways, and the carbon card.
6. **Save QR (PNG)**, open **Passport Verifier** and upload the QR image: it
   verifies. Then **Save passport (JSON)**, open the file in Notepad, copy its
   text, change one number, and paste it into the verifier: it is flagged as
   altered.
7. **The Argument / Our Research / Data Sources.** Every figure names its
   dataset, and the sources page shows how fresh each dataset is.

**Tip:** do one practice scan before the audience watches. The first
assessment after starting the backend takes 15–25 seconds while the model
loads. After that it takes about a second.

### Scanning the QR with a phone on a local demo

The QR holds `<site address>/?verify=…`. If the site is open as
`http://localhost:5173`, the QR says "localhost", which on a phone means the
phone itself, so nothing opens. On the live site this works as-is. For a local
demo:

1. Start the frontend with `npm run dev -- --host`. Vite prints a **Network**
   address such as `http://192.168.1.23:5173`.
2. On the laptop, open the site at that Network address, not localhost. If
   Windows asks, allow Node.js through the firewall on **private** networks.
3. Put the phone on the same Wi-Fi and scan the QR with its normal camera app.
   It opens the verifier with the passport already checked.

Trade-off: browsers allow the camera only on `localhost` or `https`, so on the
Network address the laptop's own **Scan with camera** button won't start.
Uploading a QR image or pasting still works. Show the phone scan instead.

## 5. Running the tests

```bat
set PYTHONPATH=.
venv\Scripts\python -m pytest
cd frontend
npm test
```

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `npm` says "running scripts is disabled" | You are in PowerShell. Switch the terminal to Command Prompt. |
| "address already in use" on port 8000 or 5173 | An old copy is still running. Close its terminal, or restart the laptop. |
| The page shows "Backend unreachable" | Terminal 1 is not running, or has not finished starting. |
| A passport made on one machine fails "issued by AfterLife" on another | Expected. Each backend signs with its own key (created in `data/keys/` on first start, never committed). |

## 7. Deploying

**Backend** (any host that runs Docker, e.g. Render or a VPS):

```bat
docker build -t afterlife-api .
docker run -p 8080:8080 ^
  -e CORS_ORIGINS=https://your-frontend.vercel.app ^
  -e AFTERLIFE_PRIVATE_KEY_B64=<base64 of the PEM private key> ^
  afterlife-api
```

`AFTERLIFE_PRIVATE_KEY_B64` keeps the signing key stable across restarts. Without
it, a new key is generated on every fresh container, and earlier passports stop
reading as issued by AfterLife.

**Frontend** (Vercel): import the repository, set the root directory to
`frontend`, and add the environment variable
`VITE_API_BASE=https://<your-backend-host>`. Vercel detects Vite and runs
`npm run build` automatically.
