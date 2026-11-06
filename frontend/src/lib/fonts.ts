import { Chonburi, Hind_Siliguri, Noto_Serif_Bengali, Nunito_Sans } from "next/font/google";

export const chonburi = Chonburi({
  variable: "--font-chonburi",
  weight: "400",
  subsets: ["latin"],
  display: "swap",
  preload: false,
});

export const notoSerifBengali = Noto_Serif_Bengali({
  variable: "--font-noto-serif-bengali",
  weight: ["700", "800"],
  subsets: ["bengali", "latin"],
  display: "swap",
  preload: false,
});

export const nunitoSans = Nunito_Sans({
  variable: "--font-nunito-sans",
  weight: ["400", "600", "700"],
  subsets: ["latin"],
  display: "swap",
  preload: false,
});

export const hindSiliguri = Hind_Siliguri({
  variable: "--font-hind-siliguri",
  weight: ["400", "500", "600"],
  subsets: ["bengali", "latin"],
  display: "swap",
  preload: false,
});

export const fontVariables = [
  chonburi.variable,
  notoSerifBengali.variable,
  nunitoSans.variable,
  hindSiliguri.variable,
].join(" ");
