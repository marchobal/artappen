// Frilägger djuret i ett foto med macOS inbyggda motivigenkänning (samma som "lyft motivet")
// och gör en 8-bitarsfigur av det: nerskalad till N×N pixlar med ett fåtal färger.
//
// Användning: swift tools/pixelate.swift <bild.jpg> <utmapp> [storlekar, t.ex. 16,24] [antal färger]
// Skriver <utmapp>/<namn>-cutout.png, <namn>-<N>.png och <namn>-palette.json
import AppKit
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

let args = CommandLine.arguments
guard args.count >= 3 else { print("användning: pixelate.swift bild utmapp [16,24] [6]"); exit(1) }
let input = URL(fileURLWithPath: args[1])
let outDir = URL(fileURLWithPath: args[2])
let sizes = (args.count > 3 ? args[3] : "16,24").split(separator: ",").compactMap { Int($0) }
let k = args.count > 4 ? Int(args[4]) ?? 6 : 6
let base = input.deletingPathExtension().lastPathComponent

func savePNG(_ img: CGImage, _ url: URL) {
    let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, img, nil)
    CGImageDestinationFinalize(dest)
}

// 1) Frilägg: största motivet (fågeln), beskuret till motivets ram
let handler = VNImageRequestHandler(url: input)
let req = VNGenerateForegroundInstanceMaskRequest()
try handler.perform([req])
guard let obs = req.results?.first, !obs.allInstances.isEmpty else { print("\(base): hittade inget motiv"); exit(2) }
// Om flera motiv: välj det största (t.ex. fågeln i stället för en gren)
var best = obs.allInstances.first!, bestArea = -1
for inst in obs.allInstances {
    let m = try obs.generateScaledMaskForImage(forInstances: IndexSet(integer: inst), from: handler)
    CVPixelBufferLockBaseAddress(m, .readOnly)
    let w = CVPixelBufferGetWidth(m), h = CVPixelBufferGetHeight(m), row = CVPixelBufferGetBytesPerRow(m)
    let p = CVPixelBufferGetBaseAddress(m)!.assumingMemoryBound(to: Float32.self)
    var area = 0
    for y in stride(from: 0, to: h, by: 4) { for x in stride(from: 0, to: w, by: 4) where p[y * row / 4 + x] > 0.5 { area += 1 } }
    CVPixelBufferUnlockBaseAddress(m, .readOnly)
    if area > bestArea { bestArea = area; best = inst }
}
let masked = try obs.generateMaskedImage(ofInstances: IndexSet(integer: best), from: handler, croppedToInstancesExtent: true)
let ctx = CIContext()
let cut = ctx.createCGImage(CIImage(cvPixelBuffer: masked), from: CIImage(cvPixelBuffer: masked).extent)!
savePNG(cut, outDir.appendingPathComponent("\(base)-cutout.png"))

// Pixelgrafik vinner på mättade färger och lite extra kontrast
let boost = CIFilter(name: "CIColorControls")!
boost.setValue(CIImage(cgImage: cut), forKey: kCIInputImageKey)
boost.setValue(1.45, forKey: kCIInputSaturationKey)
boost.setValue(1.12, forKey: kCIInputContrastKey)
let vivid = ctx.createCGImage(boost.outputImage!, from: CIImage(cgImage: cut).extent)!

// 2) Nerskalning till N×N (motivet centrerat, proportioner bevarade)
func downscale(_ img: CGImage, _ n: Int) -> [UInt8] {
    var buf = [UInt8](repeating: 0, count: n * n * 4)
    let cs = CGColorSpace(name: CGColorSpace.sRGB)!
    let c = CGContext(data: &buf, width: n, height: n, bitsPerComponent: 8, bytesPerRow: n * 4, space: cs,
                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.interpolationQuality = .high
    let inner = Double(n - 2) // en pixel kvar runt om för konturen
    let s = inner / Double(max(img.width, img.height))
    let w = Double(img.width) * s, h = Double(img.height) * s
    c.draw(img, in: CGRect(x: (Double(n) - w) / 2, y: 1, width: w, height: h)) // står på "marken"
    return buf
}

// 3) Färgschema: k-means på den frilagda bilden i större storlek, så att små men tydliga
//    fläckar (steglitsens röda ansikte, en gul näbb) får en egen färg.
func dist(_ p: [Double], _ q: [Double]) -> Double {
    let dr = p[0] - q[0], dg = p[1] - q[1], db = p[2] - q[2]
    return dr * dr * 0.3 + dg * dg * 0.59 + db * db * 0.11
}
func chroma(_ c: [Double]) -> Double { c.max()! - c.min()! }

func opaquePixels(_ px: [UInt8], _ n: Int) -> ([[Double]], [Int]) {
    var pts: [[Double]] = [], idx: [Int] = []
    for i in 0..<(n * n) where px[i * 4 + 3] > 110 {
        let a = Double(px[i * 4 + 3]) / 255
        pts.append([Double(px[i * 4]) / a, Double(px[i * 4 + 1]) / a, Double(px[i * 4 + 2]) / a]); idx.append(i)
    }
    return (pts, idx)
}

func nearest(_ p: [Double], _ cent: [[Double]]) -> Int {
    var best = 0, bd = Double.infinity
    for (c, q) in cent.enumerated() { let d = dist(p, q); if d < bd { bd = d; best = c } }
    return best
}

func palette(_ pts: [[Double]], _ k: Int) -> [[Double]] {
    // Start: medelfärgen, sedan upprepat den pixel som ligger längst från alla valda
    var cent: [[Double]] = [(0..<3).map { ch in pts.map { $0[ch] }.reduce(0, +) / Double(pts.count) }]
    var minD = pts.map { dist($0, cent[0]) }
    while cent.count < min(k, pts.count) {
        let far = minD.indices.max { minD[$0] < minD[$1] }!
        cent.append(pts[far])
        for i in pts.indices { minD[i] = min(minD[i], dist(pts[i], pts[far])) }
    }
    var assign = [Int](repeating: 0, count: pts.count)
    for _ in 0..<15 {
        for (j, p) in pts.enumerated() { assign[j] = nearest(p, cent) }
        var sum = [[Double]](repeating: [0, 0, 0], count: cent.count), cnt = [Int](repeating: 0, count: cent.count)
        for (j, p) in pts.enumerated() { for ch in 0..<3 { sum[assign[j]][ch] += p[ch] }; cnt[assign[j]] += 1 }
        for c in cent.indices where cnt[c] > 0 { cent[c] = sum[c].map { $0 / Double(cnt[c]) } }
    }
    // Varje färg = medel av den mest mättade halvan av sina pixlar (skuggor gör annars
    // accentfärger grumliga – steglitsens röda blev rödbrunt)
    for (j, p) in pts.enumerated() { assign[j] = nearest(p, cent) }
    for c in cent.indices {
        let mem = pts.indices.filter { assign[$0] == c }.sorted { chroma(pts[$0]) > chroma(pts[$1]) }
        let top = mem.prefix(max(1, mem.count / 2))
        if !top.isEmpty { cent[c] = (0..<3).map { ch in top.map { pts[$0][ch] }.reduce(0, +) / Double(top.count) } }
    }
    // Släng brus (ögonglimtar m.m. under 0,4 %) och slå ihop nästan lika färger
    var cnt = [Int](repeating: 0, count: cent.count)
    for p in pts { cnt[nearest(p, cent)] += 1 }
    var keep = cent.indices.filter { Double(cnt[$0]) / Double(pts.count) >= 0.004 }.sorted { cnt[$0] > cnt[$1] }
    var merged: [Int] = []
    for c in keep where !merged.contains(where: { dist(cent[$0], cent[c]) < 260 }) { merged.append(c) }
    keep = merged
    return keep.map { cent[$0] }
}

// 4) Pixelfigur: varje stor pixel = ett block i högupplöst bild. Vanligaste färgen i blocket vinner,
//    men en mättad accentfärg som täcker minst en femtedel av blocket får företräde.
func sprite(_ hi: [UInt8], _ n: Int, _ f: Int, _ cent: [[Double]]) -> [UInt8] {
    let H = n * f
    var out = [UInt8](repeating: 0, count: n * n * 4)
    for by in 0..<n { for bx in 0..<n {
        var counts = [Int](repeating: 0, count: cent.count), opaque = 0
        for y in (by * f)..<(by * f + f) { for x in (bx * f)..<(bx * f + f) {
            let i = (y * H + x) * 4
            if hi[i + 3] > 110 {
                let a = Double(hi[i + 3]) / 255
                counts[nearest([Double(hi[i]) / a, Double(hi[i + 1]) / a, Double(hi[i + 2]) / a], cent)] += 1
                opaque += 1
            }
        } }
        guard Double(opaque) >= Double(f * f) * 0.45 else { continue }
        var pick = counts.indices.max { counts[$0] < counts[$1] }!
        for c in counts.indices where chroma(cent[c]) > 90 && chroma(cent[c]) > chroma(cent[pick]) + 30
                                    && Double(counts[c]) >= Double(opaque) * 0.2 { pick = c }
        let o = (by * n + bx) * 4, c = cent[pick]
        out[o] = UInt8(min(255, max(0, c[0]))); out[o + 1] = UInt8(min(255, max(0, c[1])))
        out[o + 2] = UInt8(min(255, max(0, c[2]))); out[o + 3] = 255
    } }
    // Mörk kontur runt figuren (klassisk sprite-look)
    var lined = out
    for y in 0..<n { for x in 0..<n where out[(y * n + x) * 4 + 3] == 0 {
        var nb = false
        for (a, b) in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)] {
            if a < 0 || b < 0 || a >= n || b >= n { continue }
            if out[(b * n + a) * 4 + 3] == 255 { nb = true; break }
        }
        if nb { let o = (y * n + x) * 4; lined[o] = 28; lined[o + 1] = 26; lined[o + 2] = 24; lined[o + 3] = 255 }
    } }
    return lined
}

// Högupplöst rutnät: n*f pixlar, med f pixlars kant så att blocken linjerar med figurens rutor
func downscaleBlocks(_ img: CGImage, _ n: Int, _ f: Int) -> [UInt8] {
    let H = n * f
    var buf = [UInt8](repeating: 0, count: H * H * 4)
    let cs = CGColorSpace(name: CGColorSpace.sRGB)!
    let c = CGContext(data: &buf, width: H, height: H, bitsPerComponent: 8, bytesPerRow: H * 4, space: cs,
                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    c.interpolationQuality = .high
    let inner = Double((n - 2) * f)
    let s = inner / Double(max(img.width, img.height))
    let w = Double(img.width) * s, h = Double(img.height) * s
    c.draw(img, in: CGRect(x: (Double(H) - w) / 2, y: Double(f), width: w, height: h))
    return buf
}

func makeImage(_ px: [UInt8], _ n: Int) -> CGImage {
    var data = px
    let cs = CGColorSpace(name: CGColorSpace.sRGB)!
    let c = CGContext(data: &data, width: n, height: n, bitsPerComponent: 8, bytesPerRow: n * 4, space: cs,
                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    return c.makeImage()!
}

// Färgschemat räknas en gång från en högupplöst version (144 px) och används för alla storlekar
let (palPts, _) = opaquePixels(downscale(vivid, 144), 144)
let cent = palette(palPts, k)
var share = [Int](repeating: 0, count: cent.count)
for p in palPts { share[nearest(p, cent)] += 1 }
let palJSON: [[Int]] = cent.indices.sorted { share[$0] > share[$1] }.map { c in
    cent[c].map { Int(min(255, max(0, $0))) } + [share[c]] }
for n in sizes {
    let f = max(4, 144 / n)
    savePNG(makeImage(sprite(downscaleBlocks(vivid, n, f), n, f, cent), n), outDir.appendingPathComponent("\(base)-\(n).png"))
}
let palettes: [String: Any] = ["full": palJSON]
let json = try JSONSerialization.data(withJSONObject: palettes)
try json.write(to: outDir.appendingPathComponent("\(base)-palette.json"))
print("\(base): klar (\(cut.width)×\(cut.height) friläggning, \(obs.allInstances.count) motiv)")
