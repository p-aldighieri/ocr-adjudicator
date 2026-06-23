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
//
// WKWebView does NOT provide native UI for web file inputs, JS dialogs, or downloads —
// the host app must implement them (WKUIDelegate / WKDownloadDelegate). Without these,
// Settings buttons (Import dataset/adjudications, Clear all, Export) silently do nothing.

import Cocoa
import WebKit

let FIXED_PORT = 47673

func findPython() -> String {
    let candidates = ["/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
    let fm = FileManager.default
    for c in candidates where fm.isExecutableFile(atPath: c) { return c }
    return "/usr/bin/python3"
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var server: Process?
    var startURL: URL?
    var retries = 0
    var lastDownloadURL: URL?
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
        webView.uiDelegate = self                    // file pickers + JS dialogs
        window.contentView!.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func startServer() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: findPython())
        p.arguments = ["-m", "http.server", String(FIXED_PORT),
                       "--bind", "127.0.0.1", "--directory", siteDir.path]
        p.standardOutput = Pipe()
        p.standardError = Pipe()
        do { try p.run(); server = p } catch { /* maybe a prior instance is serving; load anyway */ }
        startURL = URL(string: "http://127.0.0.1:\(FIXED_PORT)/")!
        webView.load(URLRequest(url: startURL!))
    }

    // MARK: - WKNavigationDelegate

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

    // Route download-attribute links (Export JSON/CSV) to a real download.
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.shouldPerformDownload { decisionHandler(.download) }
        else { decisionHandler(.allow) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    // MARK: - WKUIDelegate (file inputs + alert/confirm/prompt)

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.canChooseFiles = true
        completionHandler(panel.runModal() == .OK ? panel.urls : nil)
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = "OCR Adjudicator"; a.informativeText = message
        a.addButton(withTitle: "OK"); a.runModal(); completionHandler()
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = "OCR Adjudicator"; a.informativeText = message
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        completionHandler(a.runModal() == .alertFirstButtonReturn)
    }
    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert(); a.messageText = "OCR Adjudicator"; a.informativeText = prompt
        let tf = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        tf.stringValue = defaultText ?? ""
        a.accessoryView = tf
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        completionHandler(a.runModal() == .alertFirstButtonReturn ? tf.stringValue : nil)
    }

    // MARK: - WKDownloadDelegate (Export JSON/CSV → ~/Downloads)

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let dir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        let fm = FileManager.default
        var url = dir.appendingPathComponent(suggestedFilename)
        let base = url.deletingPathExtension().lastPathComponent
        let ext = url.pathExtension
        var i = 1
        while fm.fileExists(atPath: url.path) {
            let name = ext.isEmpty ? "\(base) (\(i))" : "\(base) (\(i)).\(ext)"
            url = dir.appendingPathComponent(name); i += 1
        }
        lastDownloadURL = url
        completionHandler(url)
    }
    func downloadDidFinish(_ download: WKDownload) {
        if let u = lastDownloadURL { NSWorkspace.shared.activateFileViewerSelecting([u]) }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let a = NSAlert(); a.messageText = "Download failed"; a.informativeText = error.localizedDescription
        a.runModal()
    }

    // MARK: - Menu / lifecycle

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
