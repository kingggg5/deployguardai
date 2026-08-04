using System.Collections;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace DeployGuard.ReadOnlySpike;

public static class CanonicalJson
{
    private static readonly JsonSerializerOptions ReportOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    public static string Serialize(object? value)
    {
        var builder = new StringBuilder();
        Write(builder, value);
        return builder.ToString();
    }

    public static string Sha256(object? value)
    {
        var bytes = Encoding.UTF8.GetBytes(Serialize(value));
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }

    private static void Write(StringBuilder builder, object? value)
    {
        switch (value)
        {
            case null:
                builder.Append("null");
                return;
            case string text:
                builder.Append(JsonSerializer.Serialize(text));
                return;
            case bool boolean:
                builder.Append(boolean ? "true" : "false");
                return;
            case byte or sbyte or short or ushort or int or uint or long or ulong:
                builder.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
                return;
            case float number:
                WriteDouble(builder, number);
                return;
            case double number:
                WriteDouble(builder, number);
                return;
            case decimal number:
                builder.Append(number.ToString("G29", CultureInfo.InvariantCulture));
                return;
            case JsonElement element:
                WriteJsonElement(builder, element);
                return;
            case IDictionary dictionary:
                WriteDictionary(builder, dictionary);
                return;
            case IEnumerable enumerable:
                builder.Append('[');
                var first = true;
                foreach (var item in enumerable)
                {
                    if (!first) builder.Append(',');
                    Write(builder, item);
                    first = false;
                }
                builder.Append(']');
                return;
            default:
                Write(builder, JsonSerializer.SerializeToElement(value, ReportOptions));
                return;
        }
    }

    private static void WriteDictionary(StringBuilder builder, IDictionary dictionary)
    {
        builder.Append('{');
        var entries = new List<(string Key, object? Value)>();
        foreach (DictionaryEntry entry in dictionary)
        {
            entries.Add((Convert.ToString(entry.Key, CultureInfo.InvariantCulture) ?? "", entry.Value));
        }
        var first = true;
        foreach (var entry in entries.OrderBy(item => item.Key, StringComparer.Ordinal))
        {
            if (!first) builder.Append(',');
            Write(builder, entry.Key);
            builder.Append(':');
            Write(builder, entry.Value);
            first = false;
        }
        builder.Append('}');
    }

    private static void WriteDouble(StringBuilder builder, double value)
    {
        if (double.IsNaN(value) || double.IsInfinity(value))
            throw new InvalidOperationException("Canonical JSON cannot contain non-finite numbers.");
        var text = value.ToString("R", CultureInfo.InvariantCulture);
        if (!text.Contains('.', StringComparison.Ordinal)
            && !text.Contains('e', StringComparison.OrdinalIgnoreCase))
        {
            text += ".0";
        }
        builder.Append(text);
    }

    private static void WriteJsonElement(StringBuilder builder, JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                builder.Append('{');
                var first = true;
                foreach (var property in value.EnumerateObject().OrderBy(item => item.Name, StringComparer.Ordinal))
                {
                    if (!first) builder.Append(',');
                    Write(builder, property.Name);
                    builder.Append(':');
                    WriteJsonElement(builder, property.Value);
                    first = false;
                }
                builder.Append('}');
                return;
            case JsonValueKind.Array:
                builder.Append('[');
                first = true;
                foreach (var item in value.EnumerateArray())
                {
                    if (!first) builder.Append(',');
                    WriteJsonElement(builder, item);
                    first = false;
                }
                builder.Append(']');
                return;
            case JsonValueKind.String:
                Write(builder, value.GetString());
                return;
            case JsonValueKind.Number:
                builder.Append(value.GetRawText());
                return;
            case JsonValueKind.True:
                builder.Append("true");
                return;
            case JsonValueKind.False:
                builder.Append("false");
                return;
            default:
                builder.Append("null");
                return;
        }
    }
}
