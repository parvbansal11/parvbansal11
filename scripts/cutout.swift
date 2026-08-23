// Subject cutout using the system Vision matting model.
// usage: swift scripts/cutout.swift in.jpg out.png [padding-fraction]

import AppKit
import CoreImage
import Vision

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: cutout.swift <input> <output.png> [pad]\n".data(using: .utf8)!)
    exit(2)
}
let inURL = URL(fileURLWithPath: args[1])
let outURL = URL(fileURLWithPath: args[2])
let pad = args.count > 3 ? (Double(args[3]) ?? 0.04) : 0.04

guard let source = CIImage(contentsOf: inURL) else {
    FileHandle.standardError.write("cannot read \(inURL.path)\n".data(using: .utf8)!)
    exit(1)
}

let handler = VNImageRequestHandler(ciImage: source, options: [:])
let request = VNGenerateForegroundInstanceMaskRequest()
try handler.perform([request])

guard let observation = request.results?.first else {
    FileHandle.standardError.write("no foreground instance found\n".data(using: .utf8)!)
    exit(1)
}

// All instances together: the sitter plus anything they are holding.
let masked = try observation.generateMaskedImage(
    ofInstances: observation.allInstances,
    from: handler,
    croppedToInstancesExtent: false
)
var image = CIImage(cvPixelBuffer: masked)

// Trim to the opaque region, then pad so the dot grid has breathing room.
let alpha = image.applyingFilter("CIColorMatrix", parameters: [
    "inputRVector": CIVector(x: 0, y: 0, z: 0, w: 1),
    "inputGVector": CIVector(x: 0, y: 0, z: 0, w: 1),
    "inputBVector": CIVector(x: 0, y: 0, z: 0, w: 1),
    "inputAVector": CIVector(x: 0, y: 0, z: 0, w: 0),
    "inputBiasVector": CIVector(x: 0, y: 0, z: 0, w: 1),
])
let context = CIContext()
var box = image.extent
if let rect = context.createCGImage(alpha, from: alpha.extent).flatMap(opaqueBounds) {
    box = rect
}
let padX = box.width * pad
let padY = box.height * pad
box = box.insetBy(dx: -padX, dy: -padY).intersection(image.extent)
image = image.cropped(to: box).transformed(by: .init(translationX: -box.minX, y: -box.minY))

guard let cg = context.createCGImage(image, from: image.extent) else { exit(1) }
let rep = NSBitmapImageRep(cgImage: cg)
rep.size = NSSize(width: cg.width, height: cg.height)
guard let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
try png.write(to: outURL)
print("\(cg.width)x\(cg.height) -> \(outURL.path)")

func opaqueBounds(_ cg: CGImage) -> CGRect? {
    let w = cg.width, h = cg.height
    var pixels = [UInt8](repeating: 0, count: w * h)
    guard let ctx = CGContext(data: &pixels, width: w, height: h, bitsPerComponent: 8,
                              bytesPerRow: w, space: CGColorSpaceCreateDeviceGray(),
                              bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return nil }
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
    var minX = w, minY = h, maxX = -1, maxY = -1
    for y in 0..<h {
        let row = y * w
        for x in 0..<w where pixels[row + x] > 24 {
            if x < minX { minX = x }
            if x > maxX { maxX = x }
            if y < minY { minY = y }
            if y > maxY { maxY = y }
        }
    }
    guard maxX >= minX, maxY >= minY else { return nil }
    // CoreImage origin is bottom-left, the bitmap above is top-down.
    return CGRect(x: minX, y: h - 1 - maxY, width: maxX - minX + 1, height: maxY - minY + 1)
}
