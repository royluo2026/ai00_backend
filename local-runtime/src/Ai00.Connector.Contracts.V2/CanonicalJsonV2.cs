using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Ai00.Connector.Contracts.V2;

public static class CanonicalJsonV2
{
    // Protocol MAX_JSON_DEPTH: root object/array counts as 1; scalars add no depth.
    public const int MaxJsonDepth = 64;
    internal static JsonDocumentOptions DocumentOptions => new() { MaxDepth = MaxJsonDepth };
    internal static readonly JsonSerializerOptions SerializerOptions = new() { MaxDepth = MaxJsonDepth };

    public static byte[] Serialize(string json) => Serialize(Parse(json));

    public static byte[] Serialize(JsonElement value)
    {
        var text = new StringBuilder();
        try { Write(text, value); }
        catch (Exception error) when (error is InvalidOperationException or ArgumentException or FormatException)
        { throw new ProtocolV2Exception("invalid_json", error); }
        return Encoding.UTF8.GetBytes(text.ToString());
    }

    internal static JsonElement Parse(string json)
    {
        try
        {
            ValidateUnicode(json);
            using var document = JsonDocument.Parse(json, DocumentOptions);
            var value = document.RootElement.Clone();
            // Validate arbitrary payloads too, before any schema projection loses information.
            Serialize(value);
            return value;
        }
        catch (Exception error) when (error is JsonException or ArgumentException or InvalidOperationException)
        { throw new ProtocolV2Exception("invalid_json", error); }
    }

    public static string Hash(JsonElement value) => "sha256:" + HexHash(Serialize(value));
    internal static string HexHash(byte[] value) => Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant();

    private static void Write(StringBuilder text, JsonElement value, int depth = 0)
    {
        if (value.ValueKind is JsonValueKind.Object or JsonValueKind.Array && ++depth > MaxJsonDepth)
            throw new ProtocolV2Exception("json_max_depth_exceeded");
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                text.Append('{');
                var seen = new HashSet<string>(StringComparer.Ordinal);
                foreach (var property in value.EnumerateObject().OrderBy(p => p.Name, StringComparer.Ordinal))
                {
                    if (!seen.Add(property.Name)) throw new ProtocolV2Exception("duplicate_json_member");
                    if (seen.Count > 1) text.Append(',');
                    WriteString(text, property.Name);
                    text.Append(':');
                    Write(text, property.Value, depth);
                }
                text.Append('}');
                break;
            case JsonValueKind.Array:
                text.Append('[');
                var first = true;
                foreach (var item in value.EnumerateArray())
                {
                    if (!first) text.Append(',');
                    first = false;
                    Write(text, item, depth);
                }
                text.Append(']');
                break;
            case JsonValueKind.String: WriteString(text, value.GetString()!); break;
            case JsonValueKind.Number: text.Append(Number(value)); break;
            case JsonValueKind.True: text.Append("true"); break;
            case JsonValueKind.False: text.Append("false"); break;
            case JsonValueKind.Null: text.Append("null"); break;
            default: throw new ProtocolV2Exception("json_value_required");
        }
    }

    private static void ValidateUnicode(string value)
    {
        for (var i = 0; i < value.Length; i++)
        {
            if (char.IsHighSurrogate(value[i]))
            {
                if (++i >= value.Length || !char.IsLowSurrogate(value[i]))
                    throw new ProtocolV2Exception("json_surrogate_forbidden");
            }
            else if (char.IsLowSurrogate(value[i])) throw new ProtocolV2Exception("json_surrogate_forbidden");
        }
    }

    private static void WriteString(StringBuilder text, string value)
    {
        ValidateUnicode(value);
        text.Append('"');
        foreach (var c in value)
        {
            text.Append(c switch
            {
                '"' => "\\\"", '\\' => "\\\\", '\b' => "\\b", '\t' => "\\t", '\n' => "\\n",
                '\f' => "\\f", '\r' => "\\r", < ' ' => "\\u" + ((int)c).ToString("x4", CultureInfo.InvariantCulture),
                _ => c.ToString(),
            });
        }
        text.Append('"');
    }

    private static string Number(JsonElement value)
    {
        var raw = value.GetRawText();
        if (!value.TryGetDouble(out var number) || !double.IsFinite(number))
            throw new ProtocolV2Exception("json_finite_number_required");
        if (raw.IndexOfAny(['.', 'e', 'E']) < 0)
        {
            var integer = BigInteger.Parse(raw, CultureInfo.InvariantCulture);
            if (new BigInteger(number) != integer) throw new ProtocolV2Exception("json_binary64_integer_required");
        }
        if (number == 0) return "0";
        // .NET 8's round-trip format supplies the shortest binary64 digits. JCS uses
        // ECMAScript's decimal/exponent boundaries and an explicit positive exponent.
        var shortest = Math.Abs(number).ToString("R", CultureInfo.InvariantCulture).ToLowerInvariant();
        var parts = shortest.Split('e');
        var point = parts[0].IndexOf('.');
        var position = (point < 0 ? parts[0].Length : point) + (parts.Length == 2 ? int.Parse(parts[1], CultureInfo.InvariantCulture) : 0);
        var digits = parts[0].Replace(".", "");
        var leading = digits.Length - digits.TrimStart('0').Length;
        digits = digits.TrimStart('0').TrimEnd('0');
        position -= leading;
        string result;
        if (position > 0 && position <= 21)
            result = position >= digits.Length ? digits.PadRight(position, '0') : digits.Insert(position, ".");
        else if (position > -6 && position <= 0)
            result = "0." + new string('0', -position) + digits;
        else
        {
            var exponent = position - 1;
            result = digits[0] + (digits.Length > 1 ? "." + digits[1..] : "") + "e" +
                (exponent >= 0 ? "+" : "") + exponent.ToString(CultureInfo.InvariantCulture);
        }
        return number < 0 ? "-" + result : result;
    }
}
