// Poängsätter fotokandidater för pixelfigurerna (efter tools/hitta_bilder.py).
// För varje bild: hur många motiv macOS motivigenkänning hittar, om fågeln är avskuren vid kanten,
// hur stor den är, hur kompakt formen är (flygande fåglar med utbredda vingar fyller sin ram dåligt),
// ljuset på fågeln (utfrätt, djupa skuggor, hård kontrast) och om bildigenkänningen ser en fågel.
// Användning: bedom_bilder <lab/pixel/cand> slug1 slug2 …   → en JSON-rad per bild
import Foundation; import CoreGraphics; import ImageIO; import Vision; import CoreVideo

func load(_ p: String) -> CGImage? {
  guard let s = CGImageSourceCreateWithURL(URL(fileURLWithPath: p) as CFURL, nil) else { return nil }
  return CGImageSourceCreateImageAtIndex(s, 0, nil)
}
func rgba(_ img: CGImage) -> [UInt8] {
  var b = [UInt8](repeating: 0, count: img.width * img.height * 4)
  let c = CGContext(data: &b, width: img.width, height: img.height, bitsPerComponent: 8, bytesPerRow: img.width * 4,
                    space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
  c.draw(img, in: CGRect(x: 0, y: 0, width: img.width, height: img.height)); return b
}
let root = CommandLine.arguments[1]
for slug in CommandLine.arguments.dropFirst(2) {
  let dir = "\(root)/\(slug)"
  let files = ((try? FileManager.default.contentsOfDirectory(atPath: dir)) ?? []).filter { $0.hasSuffix(".jpg") }
  for f in files.sorted() {
    var out: [String: Any] = ["slug": slug, "id": Int(f.dropLast(4)) ?? -1]
    guard let img = load("\(dir)/\(f)") else { continue }
    let W = img.width, H = img.height
    let handler = VNImageRequestHandler(cgImage: img)
    let cls = VNClassifyImageRequest(), fg = VNGenerateForegroundInstanceMaskRequest()
    try? handler.perform([cls, fg])
    out["bird"] = Double((cls.results ?? []).first { $0.identifier == "bird" }?.confidence ?? 0)
    guard let obs = fg.results?.first, !obs.allInstances.isEmpty,
          let mask = try? obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler) else {
      out["score"] = -99; out["why"] = "inget motiv"; print(String(data: try! JSONSerialization.data(withJSONObject: out), encoding: .utf8)!); continue
    }
    // ytan per motiv (grovt), för att räkna hur många tydliga motiv det finns
    var areas: [Int] = []
    for inst in obs.allInstances {
      if let m = try? obs.generateScaledMaskForImage(forInstances: IndexSet(integer: inst), from: handler) {
        CVPixelBufferLockBaseAddress(m, .readOnly)
        let mw = CVPixelBufferGetWidth(m), mh = CVPixelBufferGetHeight(m), row = CVPixelBufferGetBytesPerRow(m) / 4
        let p = CVPixelBufferGetBaseAddress(m)!.assumingMemoryBound(to: Float.self)
        var a = 0; for y in stride(from: 0, to: mh, by: 3) { for x in stride(from: 0, to: mw, by: 3) where p[y * row + x] > 0.5 { a += 1 } }
        CVPixelBufferUnlockBaseAddress(m, .readOnly); areas.append(a)
      }
    }
    let big = areas.max() ?? 0
    let subjects = areas.filter { Double($0) >= Double(big) * 0.15 }.count
    // största motivet: ram, yta och ljus
    let best = obs.allInstances.sorted()[areas.firstIndex(of: big) ?? 0]
    let m = try! obs.generateScaledMaskForImage(forInstances: IndexSet(integer: best), from: handler)
    CVPixelBufferLockBaseAddress(m, .readOnly)
    let mw = CVPixelBufferGetWidth(m), mh = CVPixelBufferGetHeight(m), row = CVPixelBufferGetBytesPerRow(m) / 4
    let mp = CVPixelBufferGetBaseAddress(m)!.assumingMemoryBound(to: Float.self)
    let px = rgba(img)
    var x0 = mw, x1 = 0, y0 = mh, y1 = 0, area = 0, n = 0, hi = 0, lo = 0
    var sumL = 0.0, sumL2 = 0.0
    for y in 0..<mh { for x in 0..<mw where mp[y * row + x] > 0.5 {
      area += 1; x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
      let ix = min(W - 1, x * W / mw), iy = min(H - 1, y * H / mh), i = (iy * W + ix) * 4
      let l = (0.2126 * Double(px[i]) + 0.7152 * Double(px[i + 1]) + 0.0722 * Double(px[i + 2])) / 255
      n += 1; sumL += l; sumL2 += l * l; if l > 0.95 { hi += 1 }; if l < 0.05 { lo += 1 }
    } }
    CVPixelBufferUnlockBaseAddress(m, .readOnly)
    let bw = Double(x1 - x0 + 1), bh = Double(y1 - y0 + 1)
    let fill = Double(area) / (bw * bh), cover = Double(area) / Double(mw * mh), aspect = bw / bh
    let edge = [x0 <= 2, x1 >= mw - 3, y0 <= 2, y1 >= mh - 3].filter { $0 }.count
    let meanL = sumL / Double(max(n, 1)), sd = sqrt(max(0, sumL2 / Double(max(n, 1)) - meanL * meanL))
    let hiF = Double(hi) / Double(max(n, 1)), loF = Double(lo) / Double(max(n, 1))
    // poäng: 0 är bra, minus för varje problem
    var score = 0.0, why: [String] = []
    if subjects > 1 { score -= 3 * Double(subjects - 1); why.append("\(subjects) motiv") }
    if edge > 0 { score -= 3 * Double(edge); why.append("avskuren") }
    if cover < 0.04 { score -= 4; why.append("liten") } else if cover < 0.08 { score -= 1.5; why.append("ganska liten") }
    if cover > 0.65 { score -= 2; why.append("för nära") }
    if fill < 0.30 { score -= 3; why.append("utspridd form (flykt?)") } else if fill < 0.36 { score -= 1 }
    if aspect > 2.6 || aspect < 0.45 { score -= 1.5; why.append("långsmal ram") }
    if hiF > 0.04 { score -= min(4, hiF * 40); why.append("utfrätt") }
    if loF > 0.12 { score -= min(3, loF * 12); why.append("djupa skuggor") }
    if sd > 0.27 { score -= (sd - 0.27) * 25; why.append("hårt ljus") }
    let bird = out["bird"] as! Double
    if bird < 0.2 { score -= 2; why.append("ser inte fågel") }
    out.merge(["subjects": subjects, "edge": edge, "cover": cover, "fill": fill, "aspect": aspect, "hi": hiF, "lo": loF,
               "sd": sd, "score": score, "why": why.joined(separator: ", ")]) { $1 }
    print(String(data: try! JSONSerialization.data(withJSONObject: out), encoding: .utf8)!)
  }
}
