// Lägger frilagda PNG-bilder på en ljusgrå bakgrund och sparar som JPEG (för den lätta granskningssidan).
// Användning: flatten höjd ut-mapp in1.png in2.png …   → ut-mapp/<namn>.jpg
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

let a = CommandLine.arguments
let h = Int(a[1])!, outDir = a[2]
for path in a.dropFirst(3) {
  guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
        let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { print("kunde inte läsa \(path)"); continue }
  let w = max(1, img.width * h / img.height)
  let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
  ctx.setFillColor(CGColor(red: 0.86, green: 0.85, blue: 0.82, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
  ctx.interpolationQuality = .high
  ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
  let name = URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
  let dst = CGImageDestinationCreateWithURL(URL(fileURLWithPath: "\(outDir)/\(name).jpg") as CFURL, UTType.jpeg.identifier as CFString, 1, nil)!
  CGImageDestinationAddImage(dst, ctx.makeImage()!, [kCGImageDestinationLossyCompressionQuality: 0.72] as CFDictionary)
  CGImageDestinationFinalize(dst)
}
