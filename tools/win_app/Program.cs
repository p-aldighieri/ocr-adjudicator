// OCR Adjudicator — native Windows wrapper.
//
// A self-contained app: a WebView2 (Chromium) window pointed at the production web build +
// the dataset, both bundled next to the executable under .\site. Fully offline — the content
// is served locally by WebView2 via a virtual-host mapping; there is no network server, no
// port, and nothing leaves the machine.
//
// This mirrors the macOS .app (Swift/WKWebView + bundled local server), but uses WebView2's
// SetVirtualHostNameToFolderMapping instead of a Python http.server. That removes the runtime
// Python dependency, any port collision, and firewall prompts — the robust native equivalent.
//
// A FIXED virtual host is deliberate: IndexedDB (where adjudications are saved) is keyed by
// origin, and the origin is this host name. Keeping it constant preserves saved work across
// launches and app updates.

using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace OCRAdjudicator;

static class Program
{
    [STAThread]
    static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2); // crisp rendering on scaled displays
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new MainForm());
    }
}

public sealed class MainForm : Form
{
    private const string VirtualHost = "app.adjudicator";
    private const string StartUrl = "https://app.adjudicator/index.html";

    private readonly WebView2 _web = new();

    public MainForm()
    {
        Text = "OCR Adjudicator";
        ClientSize = new System.Drawing.Size(1280, 860);
        StartPosition = FormStartPosition.CenterScreen;
        WindowState = FormWindowState.Maximized;
        TryLoadIcon();

        _web.Dock = DockStyle.Fill;
        Controls.Add(_web);

        Load += async (_, _) => await InitAsync();
    }

    private void TryLoadIcon()
    {
        try
        {
            var ico = Path.Combine(AppContext.BaseDirectory, "app.ico");
            if (File.Exists(ico)) Icon = new System.Drawing.Icon(ico);
        }
        catch { /* non-fatal: fall back to default icon */ }
    }

    private async Task InitAsync()
    {
        var siteDir = Path.Combine(AppContext.BaseDirectory, "site");
        if (!File.Exists(Path.Combine(siteDir, "index.html")))
        {
            MessageBox.Show(
                "The bundled app files are missing (site\\index.html was not found).\n" +
                "Please reinstall OCR Adjudicator.",
                "OCR Adjudicator", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Close();
            return;
        }

        // Persist WebView2 data (IndexedDB, cache) in a stable per-user folder so saved work
        // survives app updates and moving the install folder.
        var userData = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "OCR Adjudicator", "WebView2");
        Directory.CreateDirectory(userData);

        try
        {
            var env = await CoreWebView2Environment.CreateAsync(userDataFolder: userData);
            await _web.EnsureCoreWebView2Async(env);
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "Microsoft Edge WebView2 Runtime is required but could not be initialized.\n\n" +
                "Install the Evergreen runtime from\n" +
                "https://go.microsoft.com/fwlink/p/?LinkId=2124703\n" +
                "then launch OCR Adjudicator again.\n\n" +
                "Details: " + ex.Message,
                "OCR Adjudicator", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Close();
            return;
        }

        var core = _web.CoreWebView2;

        // Serve the bundled web build + dataset from the fixed offline origin.
        core.SetVirtualHostNameToFolderMapping(
            VirtualHost, siteDir, CoreWebView2HostResourceAccessKind.Allow);

        // App feel: hide the link-hover status bar, disable edge swipe-nav (it would lose state),
        // and turn off page-level zoom so the in-app image zoom is the only zoom.
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.IsSwipeNavigationEnabled = false;
        core.Settings.IsZoomControlEnabled = false;

        // Self-contained offline app — never spawn popup windows.
        core.NewWindowRequested += (_, e) => e.Handled = true;

        core.Navigate(StartUrl);
    }
}
