using System.Text.Json;
using System.Text.Json.Serialization;

namespace Sora.DesktopWidget;

public sealed record ModelPurposeRow(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("purpose")] string Purpose);

/// <summary>Bounded descriptive draft only; never credentials, authorization or an inference call.</summary>
public sealed class ModelPurposeDraft
{
    private readonly List<ModelPurposeRow> rows = [];
    public IReadOnlyList<ModelPurposeRow> Rows => rows.AsReadOnly();

    public ModelPurposeDraft(JsonElement initial)
    {
        if (initial.ValueKind != JsonValueKind.Array) throw new ArgumentException("Model purposes must be an array.");
        foreach (var item in initial.EnumerateArray())
        {
            string id = item.GetProperty("id").GetString() ?? "";
            string purpose = item.GetProperty("purpose").GetString() ?? "";
            if (rows.Any(row => row.Id == id)) throw new ArgumentException("Duplicate exact model ID.");
            Upsert(id, purpose);
        }
    }

    public void Upsert(string id, string purpose)
    {
        if (id.Length is < 1 or > 256 || id.Any(c => char.IsWhiteSpace(c) || char.IsControl(c)))
            throw new ArgumentException("Use an exact model ID (1–256 characters, without spaces or controls).");
        if (purpose.Length > 500) throw new ArgumentException("Purpose must be at most 500 characters.");
        int index = rows.FindIndex(row => row.Id == id);
        if (index >= 0) rows[index] = new ModelPurposeRow(id, purpose);
        else
        {
            if (rows.Count >= 64) throw new ArgumentException("At most 64 model purposes per agent.");
            rows.Add(new ModelPurposeRow(id, purpose));
        }
    }

    public bool Remove(string id) => rows.RemoveAll(row => row.Id == id) != 0;
    public JsonElement ToJson() => JsonSerializer.SerializeToElement(rows);
}
