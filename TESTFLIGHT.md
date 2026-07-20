# Options Guru → TestFlight (iOS)

This repo now has three parts:

| Folder | What it is |
|--------|-----------|
| root `*.py` (`app.py`, `greeks.py`, …) | Your original **Streamlit** app + analytics — unchanged |
| [`backend/`](backend) | **FastAPI** service exposing the analytics as a JSON API |
| [`mobile/`](mobile) | **Expo** (React Native) iOS app that ships to **TestFlight** |

## Why the architecture

TestFlight only distributes **native iOS apps**, and Python can't run natively on
iOS. So the Python math becomes a small hosted **API**, and a **native app** (built
in the cloud with **EAS Build**, since you're on Windows) calls it. No Mac needed.

## The 5-step path

1. **Deploy the API.** Push this folder to GitHub → deploy with
   [`render.yaml`](render.yaml) on Render (or Docker anywhere). You get a URL like
   `https://options-guru-api.onrender.com`. Verify at `/docs`.
2. **Point the app at it.** In `mobile/`, set `EXPO_PUBLIC_API_URL` (see
   `mobile/.env.example`).
3. **Preview instantly** (optional): `cd mobile && npx expo start`, open in **Expo Go**.
4. **Build for iOS:** `cd mobile && eas build --platform ios --profile production`
   (EAS creates the Apple certificates/app record for you).
5. **Submit:** `eas submit --platform ios --latest` → the build shows up in
   **App Store Connect → TestFlight** → add testers.

Full details, including the Apple Developer / App Store Connect specifics, are in
**[`mobile/README.md`](mobile/README.md)** and **[`backend/README.md`](backend/README.md)**.

## What you need from Apple

- Apple Developer Program membership ($99/yr).
- Your **Apple ID**, **Team ID** (Apple Developer → Membership), and after the
  first build, the **App Store Connect App ID** — drop these into `mobile/eas.json`.

> Educational tool. Not investment advice.
