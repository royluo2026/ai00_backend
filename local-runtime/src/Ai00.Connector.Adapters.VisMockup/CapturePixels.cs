using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal sealed record CapturePixels(int Width, int Height, byte[] Bgr)
{
    public static void NormalizePng(string path, CaptureProfile profile)
    {
        using var source = new Bitmap(path);
        if (source.Width == profile.Width && source.Height == profile.Height) return;
        using var output = new Bitmap(profile.Width, profile.Height, PixelFormat.Format24bppRgb);
        using (var graphics = Graphics.FromImage(output))
        {
            graphics.Clear(source.GetPixel(0, 0));
            var scale = Math.Min((double)profile.Width / source.Width, (double)profile.Height / source.Height);
            var width = Math.Max(1, (int)Math.Round(source.Width * scale));
            var height = Math.Max(1, (int)Math.Round(source.Height * scale));
            graphics.DrawImage(source, new Rectangle((profile.Width - width) / 2, (profile.Height - height) / 2, width, height));
        }
        source.Dispose();
        output.Save(path, ImageFormat.Png);
    }

    public static CapturePixels Read(string path, CaptureProfile profile)
    {
        using var source = new Bitmap(path);
        if (source.Width != profile.Width || source.Height != profile.Height)
            throw new ConnectorException("capture_dimension_mismatch");
        using var image = new Bitmap(source.Width, source.Height, PixelFormat.Format24bppRgb);
        using (var graphics = Graphics.FromImage(image)) graphics.DrawImageUnscaled(source, 0, 0);
        var pixels = new byte[checked(image.Width * image.Height * 3)];
        var data = image.LockBits(new Rectangle(0, 0, image.Width, image.Height),
            ImageLockMode.ReadOnly, PixelFormat.Format24bppRgb);
        try
        {
            for (var row = 0; row < image.Height; row++)
                Marshal.Copy(IntPtr.Add(data.Scan0, row * data.Stride), pixels, row * image.Width * 3, image.Width * 3);
        }
        finally { image.UnlockBits(data); }
        return new(image.Width, image.Height, pixels);
    }

    public void RequireGrayScene()
    {
        var foreground = 0;
        var colored = 0;
        var cornerOverlay = 0;
        var left = Width;
        var right = 0;
        var top = Height;
        var bottom = 0;
        for (var row = 0; row < Height; row++)
        for (var column = 0; column < Width; column++)
        {
            var offset = (row * Width + column) * 3;
            var blue = (int)Bgr[offset];
            var green = (int)Bgr[offset + 1];
            var red = (int)Bgr[offset + 2];
            if (Math.Max(Math.Abs(blue - Bgr[0]), Math.Max(Math.Abs(green - Bgr[1]), Math.Abs(red - Bgr[2]))) < 20)
                continue;
            foreground++;
            if (Math.Max(red, Math.Max(green, blue)) - Math.Min(red, Math.Min(green, blue)) > 25)
            {
                colored++;
                // Native capture includes the coordinate triad. Exempt only a
                // small bottom-left annotation budget, never a large colored part.
                if (column < Width / 5 && row >= Height * 3 / 4) cornerOverlay++;
            }
            left = Math.Min(left, column); right = Math.Max(right, column);
            top = Math.Min(top, row); bottom = Math.Max(bottom, row);
        }
        if (foreground < 5000 || Math.Max((right - left + 1.0) / Width, (bottom - top + 1.0) / Height) < .15)
            throw new ConnectorException("capture_empty_or_clipped_scene");
        var annotation = cornerOverlay <= Width * Height / 1000 ? cornerOverlay : 0;
        if (colored - annotation > Math.Max(300, foreground / 50))
            throw new ConnectorException("capture_gray_baseline_invalid");
    }

    public void RequireBlueResponse(CapturePixels blue)
    {
        if (Width != blue.Width || Height != blue.Height)
            throw new ConnectorException("capture_dimension_mismatch");
        var count = 0;
        long horizontal = 0, vertical = 0;
        for (var row = 0; row < Height; row++)
        for (var column = 0; column < Width; column++)
        {
            var offset = (row * Width + column) * 3;
            var change = Math.Max(Math.Abs(blue.Bgr[offset] - Bgr[offset]),
                Math.Max(Math.Abs(blue.Bgr[offset + 1] - Bgr[offset + 1]), Math.Abs(blue.Bgr[offset + 2] - Bgr[offset + 2])));
            if (change < 25 || blue.Bgr[offset] - Math.Max(blue.Bgr[offset + 1], blue.Bgr[offset + 2]) < 35
                || blue.Bgr[offset] - Bgr[offset] < 20) continue;
            count++; horizontal += column; vertical += row;
        }
        if (count < 30) throw new ConnectorException("capture_target_not_blue_or_occluded");
        var horizontalOffset = (double)horizontal / count / Width - .5;
        var verticalOffset = (double)vertical / count / Height - .5;
        if (Math.Sqrt(horizontalOffset * horizontalOffset + verticalOffset * verticalOffset) > .48)
            throw new ConnectorException("capture_target_not_blue_or_occluded");
    }
}
