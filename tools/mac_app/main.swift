// OCR Adjudicator — native macOS wrapper.
//
// A self-contained .app: a WKWebView window pointed at a tiny local static server
// (Python's http.server, system-provided) that serves the production web build + the
// dataset, both bundled inside Contents/Resources/site. Fully offline — the server
// binds to 127.0.0.1 only; nothing leaves the machine.
//
// A FIXED loopback port is used on purpose: IndexedDB (where adjudications are saved)
// is keyed by origin, and origin includes the port — a fixed port keeps your saved work
// across launches. If a prior instance is already serving that port, we just reuse it.

import Cocoa
import WebKit

let FIXED_PORT = 47673

func findPython() -> String {
    let candidates = ["/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
    let fm = FileManager.default
    for c in candidates where fm.isExecutableFile(atPath: c) { return c }
    return "/usr/bin/python3"
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var server: Process?
    var startURL: URL?
    var retries = 0
    let siteDir = Bundle.main.resourceURL!.appendingPathComponent("site")

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenu()
        setupWindow()
        startServer()
    }

    func setupWindow() {
        let rect = NSRect(x: 0, y: 0, width: 1280, height: 860)
        window = NSWindow(contentRect: rect,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "OCR Adjudicator"
        window.center()
        window.setFrameAutosaveName("OCRAdjudicatorMain")
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()            // persistent IndexedDB store
        webView = WKWebView(frame: window.contentView!.bounds, configuration: cfg)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        window.contentView!.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func startServer() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: findPython())
        p.arguments = ["-m", "http.server", String(FIXED_PORT),
                       "--bind", "127.0.0.1", "--directory", siteDir.path]
        p.standardOutput = Pipe()                    // discard server logs
        p.standardError = Pipe()
        do { try p.run(); server = p } catch { /* maybe a prior instance is serving; load anyway */ }
        startURL = URL(string: "http://127.0.0.1:\(FIXED_PORT)/")!
        webView.load(URLRequest(url: startURL!))     // retried below until the server answers
    }

    // The first load(s) may race the server starting up — keep retrying briefly.
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard let url = startURL, retries < 40 else {
            if retries >= 40 {
                let a = NSAlert()
                a.messageText = "OCR Adjudicator couldn’t start"
                a.informativeText = "The local server didn’t come up on port \(FIXED_PORT). It may be in use by another app."
                a.runModal()
            }
            return
        }
        retries += 1
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
            webView.load(URLRequest(url: url))
        }
    }

    func buildMenu() {
        let mainMenu = NSMenu()

        let appItem = NSMenuItem(); mainMenu.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "Hide OCR Adjudicator", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit OCR Adjudicator", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let editItem = NSMenuItem(); mainMenu.addItem(editItem)
        let editMenu = NSMenu(title: "Edit"); editItem.submenu = editMenu
        editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(NSMenuItem.separator())
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        NSApp.mainMenu = mainMenu
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ note: Notification) { server?.terminate() }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
