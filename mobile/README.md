# Options Guru — iOS (Expo) app

A native React Native app that puts Options Guru on your iPhone and ships to
**TestFlight**. It talks to the FastAPI backend in [`../backend`](../backend),
which reuses your existing Python analytics (`greeks.py`, `significance.py`,
`risk_rating.py`, `scanner.py`, `data.py`).

Because you're on **Windows**, iOS builds are done in the cloud with
**EAS Build** — no Mac or Xcode required.

```
Options Guru/
├── app.py, greeks.py, ...   ← original Streamlit app + analytics (unchanged)
├── backend/                 ← FastAPI wrapper around the analytics (deploy this)
└── mobile/                  ← this Expo app (build → TestFlight)
```

---

## 0. Prerequisites (one-time)

- **Node.js** (already installed) and this repo.
- An **Apple Developer account** ($99/yr) with access to **App Store Connect**.
- A free **Expo account** — sign up at https://expo.dev.
- Install the EAS CLI:  `npm install -g eas-cli`

---

## 1. Deploy the backend (so the phone can reach it)

The app needs the API on a public URL. Easiest free option is **Render** using the
included [`../render.yaml`](../render.yaml):

1. Push this whole `Options Guru` folder to a GitHub repo.
2. On https://render.com → **New → Blueprint**, point it at the repo. It reads
   `render.yaml` and deploys `options-guru-api`.
3. Note the URL it gives you, e.g. `https://options-guru-api.onrender.com`.
4. Test it: open `https://<your-url>/docs` in a browser — you should see the API.

> Alternatives: Railway, Fly.io, or any host that runs
> `uvicorn backend.main:app`. See [`../backend/README.md`](../backend/README.md).

---

## 2. Point the app at your backend

Set the API URL the app should call. Two ways:

- **Env file (recommended):** copy `.env.example` → `.env` and set
  `EXPO_PUBLIC_API_URL=https://<your-render-url>`
- Or edit the `FALLBACK` constant in [`src/config.ts`](src/config.ts).

For **local testing on your phone over Wi-Fi**, use your computer's LAN IP
(e.g. `http://192.168.1.42:8000`), not `localhost` — the phone can't reach the
laptop's localhost.

---

## 3. Try it instantly with Expo Go (before any TestFlight build)

This is the fastest way to see it on your phone while iterating:

```bash
cd mobile
npm install                 # first time only
npx expo start
```

Install **Expo Go** from the App Store, then scan the QR code in the terminal.
(Run the backend locally with `uvicorn` and set `EXPO_PUBLIC_API_URL` to your
LAN IP for this.)

---

## 4. Build for TestFlight with EAS

```bash
cd mobile
eas login                   # use your Expo account
eas build:configure         # links project; fills extra.eas.projectId in app.json
```

Then kick off a cloud iOS build:

```bash
eas build --platform ios --profile production
```

- On first run EAS asks to **log in with your Apple ID** and will create the
  App Store Connect app record, signing certificate, and provisioning profile
  **for you** (choose "let EAS manage credentials"). No Mac needed.
- When it finishes you get an `.ipa` built in the cloud.

### Submit the build to TestFlight

```bash
eas submit --platform ios --profile production --latest
```

Fill in your real Apple details in [`eas.json`](eas.json) first
(`appleId`, `ascAppId`, `appleTeamId`), or let the prompts guide you.
`ascAppId` is the numeric App ID from App Store Connect → your app → App Information.

You can also combine build + submit:
`eas build --platform ios --profile production --auto-submit`

---

## 5. Enable TestFlight testing

1. In **App Store Connect → your app → TestFlight**, the uploaded build appears
   after ~5–15 min of processing.
2. Answer the **Export Compliance** question — the app sets
   `ITSAppUsesNonExemptEncryption = false` (it uses only standard HTTPS), so you
   can select "No" for custom encryption.
3. Add yourself (and testers) under **Internal Testing**, or create an external
   group. Testers install the **TestFlight** app and accept the invite.

That's it — Options Guru runs on the iPhone via TestFlight.

---

## Updating the app later

- Change code → bump `ios.buildNumber` in `app.json` (or rely on
  `autoIncrement` in the production profile) → `eas build ... --auto-submit`.
- For pure JS/content changes you can later add **EAS Update** (OTA) to push
  updates without a new TestFlight build.

## Notes / limitations

- Data is live from Yahoo Finance via the backend; if the free Render instance
  is asleep, the first request may take ~30–60s to wake it.
- The scanner endpoint scans ~40 names by default to stay within mobile timeouts.
- Educational tool — not investment advice.
