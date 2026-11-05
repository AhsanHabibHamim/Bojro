import { ImageResponse } from "next/og";

export const size = {
  width: 180,
  height: 180,
};

export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    <div
      style={{
        alignItems: "center",
        background: "linear-gradient(135deg, #2A1565, #5B2FC9, #7C4DFF)",
        display: "flex",
        height: "100%",
        justifyContent: "center",
        width: "100%",
      }}
    >
      <div
        style={{
          background: "white",
          clipPath: "polygon(58% 0, 12% 56%, 44% 56%, 30% 100%, 88% 40%, 54% 40%)",
          display: "flex",
          height: 118,
          width: 86,
        }}
      />
    </div>,
    size,
  );
}
