// Skogsförlust över Sverige år för år, ur Hansen m.fl. Global Forest Change (via Global Forest Watch:s kartrutor).
// Användning: swift tools/skog_forlust.swift data/skog/forlust.png [cachemapp]
//
// GFW:s rutor (tcd_30 = trädtäcke över 30 % år 2000) har förlustens år i blå kanal (1–25 = 2001–2025)
// och hur mycket skog som försvann i pixeln i röd kanal. Blå 0 är en svag gloria kring hyggena och räknas inte.
// Skogen år 2000 kommer från GFW:s rutor för trädtäcke (umd_tree_cover_density_2000, tcd_30): en ren mask, skog eller inte.
// Utdata är en PNG utan färgprofil, så att värdena kommer fram exakt:
//   röd = år efter 2000 (0 = ingen förlust), grön = mängd förlust (0–255), blå = 255 där det var skog år 2000.
// Bilden täcker samma Web Mercator-ruta som landskapet (trend/landskap.html), norr överst.
import Foundation
import CoreGraphics
import ImageIO
import zlib

let args = CommandLine.arguments
guard args.count > 1 else { print("Användning: swift tools/skog_forlust.swift ut.png [cachemapp]"); exit(1) }
let outPath = args[1]
let cache = URL(fileURLWithPath: args.count > 2 ? args[2] : NSTemporaryDirectory()).appendingPathComponent("gfw_tcd30")
try? FileManager.default.createDirectory(at: cache, withIntermediateDirectories: true)

let VERSION = "v1.13", ZOOM = 7, TILE = 512, F = 2   // zoom 7 med 512-pixlarsrutor ≈ 145 m per pixel i Sverige; F=2 ger ≈ 290 m
let UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp)"
func merc(_ lat: Double, _ lon: Double) -> (Double, Double) {
    let la = lat * .pi / 180
    return ((lon + 180) / 360, (1 - log(tan(la) + 1 / cos(la)) / .pi) / 2)
}
let (x0, y0) = merc(69.06, 10.95), (x1, y1) = merc(55.33, 24.17)
let world = Double((1 << ZOOM) * TILE)
let sx0 = Int((x0 * world).rounded()), sy0 = Int((y0 * world).rounded())
let W = Int(((x1 - x0) * world / Double(F)).rounded()), H = Int(((y1 - y0) * world / Double(F)).rounded())
print("Utdata \(W) × \(H) pixlar")

// ---- rutorna ----
let LOSS = "umd_tree_cover_loss/\(VERSION)/tcd_30", FOREST = "umd_tree_cover_density_2000/v1.8/tcd_30"
var tiles: [String: [UInt8]] = [:]
// size: förlustrutorna är 512 pixlar, trädtäckets 256 (samma rutnät som utdata, eftersom F = 2)
func fetchTile(_ layer: String, _ size: Int, _ tx: Int, _ ty: Int) -> [UInt8] {
    let key = "\(tx)_\(ty)", prefix = layer == LOSS ? "" : "tcd2000_"
    if let t = tiles[prefix + key] { return t }
    let file = cache.appendingPathComponent("\(prefix)\(ZOOM)_\(key).png")
    var data = try? Data(contentsOf: file)
    if data == nil {
        let url = URL(string: "https://tiles.globalforestwatch.org/\(layer)/\(ZOOM)/\(tx)/\(ty).png")!
        for attempt in 0..<5 {
            var req = URLRequest(url: url, timeoutInterval: 60); req.setValue(UA, forHTTPHeaderField: "User-Agent")
            let sem = DispatchSemaphore(value: 0); var got: Data? = nil; var code = 0
            URLSession.shared.dataTask(with: req) { d, r, _ in got = d; code = (r as? HTTPURLResponse)?.statusCode ?? 0; sem.signal() }.resume()
            sem.wait()
            if code == 200, let g = got { data = g; try? g.write(to: file); break }
            if code == 404 || code == 204 { break }            // ingen ruta = ingen skogsförlust där
            print("  ruta \(key): svar \(code), försöker igen"); sleep(UInt32(1 << attempt))
        }
    }
    var px = [UInt8](repeating: 0, count: size * size * 4)
    if let d = data, !d.isEmpty, let src = CGImageSourceCreateWithData(d as CFData, nil),
       let img = CGImageSourceCreateImageAtIndex(src, 0, nil) {
        // Rita i bildens egen färgrymd, så att inga värden räknas om
        let cs = (img.colorSpace?.model == .rgb ? img.colorSpace : nil) ?? CGColorSpace(name: CGColorSpace.sRGB)!
        let ctx = CGContext(data: &px, width: size, height: size, bitsPerComponent: 8, bytesPerRow: size * 4,
                            space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: size, height: size))
    }
    tiles[prefix + key] = px
    return px
}

// ---- sammanställning: F × F källpixlar blir en ----
var out = [UInt8](repeating: 0, count: W * H * 3)
var perYear = [Int](repeating: 0, count: 26), forest = 0
for oy in 0..<H {
    for ox in 0..<W {
        var sum = 0, bestR = 0, bestYear = 0
        for dy in 0..<F { for dx in 0..<F {
            let wx = sx0 + ox * F + dx, wy = sy0 + oy * F + dy
            let t = fetchTile(LOSS, TILE, wx / TILE, wy / TILE)
            let i = ((wy % TILE) * TILE + (wx % TILE)) * 4
            let r = Int(t[i]), b = Int(t[i + 2]), a = t[i + 3]
            if a == 255 && b >= 1 && b <= 25 {
                sum += r
                if r > bestR { bestR = r; bestYear = b }
            }
        } }
        let o = (oy * W + ox) * 3
        // skogen år 2000: en pixel i trädtäckets 256-rutor motsvarar exakt en utdatapixel
        let fx = sx0 / F + ox, fy = sy0 / F + oy, T2 = TILE / F
        let ft = fetchTile(FOREST, T2, fx / T2, fy / T2)
        if ft[((fy % T2) * T2 + (fx % T2)) * 4 + 3] == 255 { out[o + 2] = 255; forest += 1 }
        if bestYear > 0 {
            // mängden i 16 nivåer räcker för bilden och packas mycket bättre
            out[o] = UInt8(bestYear); out[o + 1] = UInt8(min(15, (sum / (F * F) + 8) / 17) * 17); perYear[bestYear] += 1
        }
    }
    if oy % 400 == 0 { print("  rad \(oy) av \(H), \(tiles.count) rutor") }
}
print("  skog år 2000: \(forest) pixlar av \(W * H)")
for y in 1...25 { print("  \(2000 + y): \(perYear[y]) pixlar") }

// ---- PNG utan färgprofil ----
func crc(_ type: [UInt8], _ body: [UInt8]) -> UInt32 {
    var c = crc32(0, nil, 0)
    c = crc32(c, type, uInt(type.count)); c = crc32(c, body, uInt(body.count))
    return UInt32(c)
}
func be(_ v: UInt32) -> [UInt8] { [UInt8(v >> 24), UInt8((v >> 16) & 255), UInt8((v >> 8) & 255), UInt8(v & 255)] }
func chunk(_ name: String, _ body: [UInt8]) -> [UInt8] {
    let t = Array(name.utf8)
    return be(UInt32(body.count)) + t + body + be(crc(t, body))
}
var raw = [UInt8](); raw.reserveCapacity(H * (W * 3 + 1))
for y in 0..<H {
    raw.append(1)                                     // filter Sub: bra för långa nollrader
    for x in 0..<(W * 3) {
        let v = out[y * W * 3 + x], left = x >= 3 ? out[y * W * 3 + x - 3] : 0
        raw.append(v &- left)
    }
}
var destLen = compressBound(uLong(raw.count))
var comp = [UInt8](repeating: 0, count: Int(destLen))
guard compress2(&comp, &destLen, raw, uLong(raw.count), 9) == Z_OK else { print("Komprimeringen misslyckades"); exit(1) }
let ihdr = be(UInt32(W)) + be(UInt32(H)) + [8, 2, 0, 0, 0]   // 8 bitar, RGB
let png: [UInt8] = [137, 80, 78, 71, 13, 10, 26, 10] + chunk("IHDR", ihdr) + chunk("IDAT", Array(comp[0..<Int(destLen)])) + chunk("IEND", [])
let outURL = URL(fileURLWithPath: outPath)
try? FileManager.default.createDirectory(at: outURL.deletingLastPathComponent(), withIntermediateDirectories: true)
try! Data(png).write(to: outURL)
print("Sparat \(outPath): \(png.count / 1024) kB")
