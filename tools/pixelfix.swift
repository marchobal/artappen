// Rättar enstaka pixlar i en pixelfigur för hand (efter granskningen).
// Användning: pixelfix <figur.png> x,y,#rrggbb … x,y,- … #gammal>#ny   (- = genomskinlig, 0,0 är övre vänstra hörnet)
// Första gången sparas originalet som <namn>.orig.png bredvid, så att det går att ångra.
import Foundation; import CoreGraphics; import ImageIO; import UniformTypeIdentifiers
let a = CommandLine.arguments, path = a[1]
let orig = path.replacingOccurrences(of: ".png", with: ".orig.png")
if !FileManager.default.fileExists(atPath: orig) { try! FileManager.default.copyItem(atPath: path, toPath: orig) }
let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil)!
let img = CGImageSourceCreateImageAtIndex(src, 0, nil)!
let w = img.width, h = img.height
var buf = [UInt8](repeating: 0, count: w * h * 4)
let ctx = CGContext(data: &buf, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                    space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
func hex(_ t: Substring) -> (UInt8, UInt8, UInt8) { let v = UInt32(t.dropFirst(), radix: 16)!; return (UInt8(v >> 16 & 255), UInt8(v >> 8 & 255), UInt8(v & 255)) }
for e in a.dropFirst(2) {
  // #gammal>#ny byter en färg överallt i figuren
  if e.contains(">") {
    let parts = e.split(separator: ">"), (r0, g0, b0) = hex(parts[0]), (r1, g1, b1) = hex(parts[1])
    for i in stride(from: 0, to: buf.count, by: 4) where buf[i + 3] == 255 && buf[i] == r0 && buf[i + 1] == g0 && buf[i + 2] == b0 {
      buf[i] = r1; buf[i + 1] = g1; buf[i + 2] = b1 }
    continue
  }
  let p = e.split(separator: ","), x = Int(p[0])!, y = Int(p[1])!, i = (y * w + x) * 4
  if p[2] == "-" { buf[i] = 0; buf[i + 1] = 0; buf[i + 2] = 0; buf[i + 3] = 0; continue }
  let v = UInt32(p[2].dropFirst(), radix: 16)!
  buf[i] = UInt8(v >> 16 & 255); buf[i + 1] = UInt8(v >> 8 & 255); buf[i + 2] = UInt8(v & 255); buf[i + 3] = 255
}
let dst = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(dst, ctx.makeImage()!, nil); CGImageDestinationFinalize(dst)
