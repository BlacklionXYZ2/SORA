using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Sora.DesktopShell;

public sealed record PanelApiResponse(int Status, string Body)
{
    public static PanelApiResponse Error(int status, string message, string code) =>
        new(status, JsonSerializer.Serialize(new { error = new { message, code } }));
}

// Forwards a web panel's same-origin /api/v1/ call to the owner's Core with the owner token.
// SoraShell's WebView2 request filter calls this, so the token never reaches page code and
// pages need no cross-origin access. scripts/panels-dev-server.py applies the same rules.
public sealed class PanelApiProxy : IDisposable
{
    public const string Host = "panels.sora.example";
    public const int MaxBodyBytes = 262_144;
    private readonly HttpClient client;
    private readonly string tokenFile;
    private readonly Func<string?> coreInstance;

    public PanelApiProxy(Uri coreUrl, string tokenFile, Func<string?> coreInstance,
        HttpMessageHandler? handler = null)
    {
        if (coreUrl.Scheme != Uri.UriSchemeHttp || coreUrl.Host is not ("127.0.0.1" or "::1" or "[::1]"))
            throw new ArgumentException("Core address must be loopback HTTP.", nameof(coreUrl));
        this.tokenFile = Path.GetFullPath(tokenFile);
        this.coreInstance = coreInstance;
        client = handler is null ? new HttpClient(new SocketsHttpHandler { UseProxy = false })
            : new HttpClient(handler);
        client.BaseAddress = coreUrl;
        client.Timeout = Timeout.InfiniteTimeSpan;
    }

    /// <summary>The Core path to forward to, or null when the page asked for something else.</summary>
    public static string? CorePath(string method, string uri)
    {
        if (method is not ("GET" or "POST") || !Uri.TryCreate(uri, UriKind.Absolute, out var parsed)
            || parsed.Scheme != Uri.UriSchemeHttps || !string.Equals(parsed.Host, Host, StringComparison.OrdinalIgnoreCase)
            || !parsed.IsDefaultPort) return null;
        var path = parsed.AbsolutePath;
        // Uri normalises "/api/v1/../x" to "/api/x", so this also refuses traversal.
        var rawPath = uri.Split('?', 2)[0];
        if (!path.StartsWith("/api/v1/", StringComparison.Ordinal) || path.Contains("//", StringComparison.Ordinal)
            || rawPath.Contains("..", StringComparison.Ordinal)) return null;
        return path + parsed.Query;
    }

    public async Task<PanelApiResponse> ForwardAsync(string method, string uri, string? body,
        CancellationToken cancellationToken)
    {
        var path = CorePath(method, uri);
        if (path is null)
            return PanelApiResponse.Error(404, "Panels may only call /api/v1/ routes.", "PANEL_ROUTE_REFUSED");
        if (body is not null && Encoding.UTF8.GetByteCount(body) > MaxBodyBytes)
            return PanelApiResponse.Error(413, "Request too large.", "PANEL_BODY_TOO_LARGE");
        string token;
        try { token = (await File.ReadAllTextAsync(tokenFile, cancellationToken)).Trim(); }
        catch (IOException) { token = ""; }
        catch (UnauthorizedAccessException) { token = ""; }
        if (token.Length < 16)
            return PanelApiResponse.Error(503, "SORA's Core is starting; its token is not ready yet.", "CORE_UNAVAILABLE");
        using var request = new HttpRequestMessage(new HttpMethod(method), path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        request.Headers.Add("X-SORA-Device-ID", "device-local");
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (coreInstance() is { } instance && path != "/api/v1/runtime/identity")
            request.Headers.Add("X-SORA-Core-Instance", instance);
        if (body is not null && method == "POST")
            request.Content = new StringContent(body, Encoding.UTF8, "application/json");
        try
        {
            using var response = await client.SendAsync(request, cancellationToken);
            var content = await response.Content.ReadAsStringAsync(cancellationToken);
            return new PanelApiResponse((int)response.StatusCode, content.Length == 0 ? "{}" : content);
        }
        catch (HttpRequestException)
        {
            return PanelApiResponse.Error(503, "SORA's Core is not reachable.", "CORE_UNAVAILABLE");
        }
    }

    public static string ReasonPhrase(int status) =>
        Enum.IsDefined(typeof(HttpStatusCode), status) ? ((HttpStatusCode)status).ToString() : "Status";

    public void Dispose() => client.Dispose();
}
