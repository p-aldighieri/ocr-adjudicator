# Installing OCR Adjudicator on your Pixel

One-time setup, ~3 minutes. After this it runs fully offline (airplane mode is fine).

## Before you start
- Phone and PC on the **same Wi-Fi** (only needed for the one-time data download).
- On the PC, the dataset server must be running. It usually is; to (re)start it, run from the
  `ocr-adjudicator` folder:
  ```
  python -m http.server 8000 -d public
  ```

## Step 1 — Install the app (the icon on your home screen)
1. On the Pixel, open **Chrome** and go to: **https://p-aldighieri.github.io/ocr-adjudicator/**
2. Tap the Chrome menu **⋮** → **Install app** (or **Add to Home screen**) → **Install**.
3. You now have an **OCR Adjudicator** icon in your app drawer / home screen. Open it — it runs
   full-screen, like a normal app. It'll show a "No dataset loaded yet" screen; that's expected.

## Step 2 — Load the data (one time)
1. In Chrome on the Pixel, open: **http://192.168.0.232:8000/dataset.zip**
   → it downloads `dataset.zip` (~318 MB) to your phone's **Downloads**. (Leave it as a .zip; don't unzip.)
2. Open the **OCR Adjudicator** app → **⚙ Settings** → **Import dataset .zip**.
3. Pick `dataset.zip` from **Downloads**. Wait for "Importing …" to finish (a minute or two — keep
   the app in the foreground). It lands on the **Overview** screen with all 1,472 university-years.

That's it — the scans now live on the phone. You can turn Wi-Fi off and keep working.

## Step 3 — Start adjudicating
- Tap **Adjudicate →** (or any cell in the Overview grid) to open a university-year.
- Pinch-zoom the scan; the **yellow row** and **cyan column** highlight where each value is.
- For each value: tap **Claude** / **Codex**, or type your own; or **Can't read** / **Wrong page**.
- Agreed values are pre-selected → just tap **Confirm & Next →**.
- Your choices save instantly and survive closing the app.

## Getting your work back to the PC
**⚙ Settings → Export JSON** (or CSV) → share the file to yourself (Drive, email, USB). On the PC:
`python tools/apply_results.py adjudications.json` merges it back into the data.

## Notes / troubleshooting
- Use **Chrome** to install (it's the Pixel default). If you only see "Add to Home screen," that's the
  same thing.
- App **features** update automatically when you reopen it. If you ever rebuild the dataset, re-import
  the new `dataset.zip` (it replaces the old one).
- The data download in Step 2 needs the PC server running and the same Wi-Fi. Alternatively, copy
  `public/dataset.zip` to the phone via USB or Google Drive and import it the same way.
- IP `192.168.0.232` is this PC's current Wi-Fi address; if your network changes it, find the new one
  with `ipconfig` (IPv4 Address) and use that.
