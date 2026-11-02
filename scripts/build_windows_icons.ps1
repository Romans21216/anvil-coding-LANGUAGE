$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$sourceRoot = Join-Path $PSScriptRoot '..\assets\icons\source'
$outputRoot = Join-Path $PSScriptRoot '..\assets\icons'
$iconSourceNames = @{
    'anvil-project.png' = 'anvil-project.ico'
    'anvil-executable.png' = 'anvil-executable.ico'
    'anvil-source.png' = 'anvil-source.ico'
}

$iconBuilderSource = @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;

public static class AnvilIconBuilder
{
    public static void Build(string sourcePath, string outputPath)
    {
        using (var source = new Bitmap(sourcePath))
        {
            int minX = source.Width, minY = source.Height, maxX = -1, maxY = -1;
            for (int y = 0; y < source.Height; ++y)
            for (int x = 0; x < source.Width; ++x)
            {
                if (source.GetPixel(x, y).A == 0) continue;
                if (x < minX) minX = x;
                if (x > maxX) maxX = x;
                if (y < minY) minY = y;
                if (y > maxY) maxY = y;
            }
            if (maxX < minX || maxY < minY)
                throw new InvalidDataException("Icon source has no visible pixels: " + sourcePath);

            var crop = Rectangle.FromLTRB(minX, minY, maxX + 1, maxY + 1);
            int contentSide = Math.Max(crop.Width, crop.Height);
            int padding = Math.Max(2, (int)Math.Ceiling(contentSide * 0.06));
            int side = contentSide + padding * 2;
            using (var master = new Bitmap(side, side, PixelFormat.Format32bppArgb))
            using (var mg = Graphics.FromImage(master))
            {
                mg.Clear(Color.Transparent);
                mg.InterpolationMode = InterpolationMode.NearestNeighbor;
                mg.PixelOffsetMode = PixelOffsetMode.Half;
                mg.DrawImage(source,
                    new Rectangle(padding + (contentSide - crop.Width) / 2,
                                  padding + (contentSide - crop.Height) / 2,
                                  crop.Width, crop.Height), crop, GraphicsUnit.Pixel);

                int[] sizes = new int[] { 16, 24, 32, 48, 64, 128, 256 };
                using (var output = File.Create(outputPath))
                using (var writer = new BinaryWriter(output))
                {
                    writer.Write((ushort)0);
                    writer.Write((ushort)1);
                    writer.Write((ushort)sizes.Length);
                    uint offset = (uint)(6 + 16 * sizes.Length);
                    var images = new byte[sizes.Length][];
                    for (int i = 0; i < sizes.Length; ++i)
                    {
                        int size = sizes[i];
                        using (var bitmap = new Bitmap(size, size, PixelFormat.Format32bppArgb))
                        using (var g = Graphics.FromImage(bitmap))
                        using (var stream = new MemoryStream())
                        {
                            g.Clear(Color.Transparent);
                            g.InterpolationMode = InterpolationMode.NearestNeighbor;
                            g.PixelOffsetMode = PixelOffsetMode.Half;
                            g.DrawImage(master, new Rectangle(0, 0, size, size));
                            bitmap.Save(stream, ImageFormat.Png);
                            images[i] = stream.ToArray();
                        }
                        writer.Write((byte)(size == 256 ? 0 : size));
                        writer.Write((byte)(size == 256 ? 0 : size));
                        writer.Write((byte)0);
                        writer.Write((byte)0);
                        writer.Write((ushort)1);
                        writer.Write((ushort)32);
                        writer.Write((uint)images[i].Length);
                        writer.Write(offset);
                        offset += (uint)images[i].Length;
                    }
                    foreach (var image in images) writer.Write(image);
                }
            }
        }
    }
}
'@

if (-not ('AnvilIconBuilder' -as [type])) {
    Add-Type -TypeDefinition $iconBuilderSource -ReferencedAssemblies 'System.Drawing'
}

foreach ($sourceName in $iconSourceNames.Keys) {
    $sourcePath = Join-Path $sourceRoot $sourceName
    $outputPath = Join-Path $outputRoot $iconSourceNames[$sourceName]
    [AnvilIconBuilder]::Build($sourcePath, $outputPath)
    Write-Output "Created $outputPath"
}
