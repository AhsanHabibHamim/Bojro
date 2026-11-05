import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "বজ্র | Bojro",
    short_name: "বজ্র",
    description: "বাংলাদেশের জন্য বাংলা-প্রথম শপিং অভিজ্ঞতা।",
    start_url: "/bn",
    scope: "/",
    display: "standalone",
    background_color: "#F7F5FC",
    theme_color: "#2A1565",
    lang: "bn",
    icons: [
      {
        src: "/pwa-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/pwa-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/pwa-maskable.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
