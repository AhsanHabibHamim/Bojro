import type { AppLocale } from "@/i18n/routing";

export const launchCopy = {
  bn: {
    page: {
      title: "পেজটি এখন দেখানো যাচ্ছে না",
      description: "সমস্যাটি এই পেজেই সীমাবদ্ধ রাখা হয়েছে। আবার চেষ্টা করলে আপনার অবস্থান থাকবে।",
    },
    commerce: {
      title: "নিরাপদ কেনাকাটায় সাময়িক সমস্যা হয়েছে",
      description: "আপনার কার্ট ও ফর্মের তথ্য সুরক্ষিত আছে। সংযোগ ঠিক হলে আবার চেষ্টা করুন।",
    },
    global: {
      title: "বজ্র সাময়িকভাবে থেমে গেছে",
      description: "একটি অপ্রত্যাশিত সমস্যা হয়েছে। নিরাপদে পেজটি আবার চালু করুন।",
    },
    server: {
      title: "সার্ভারে সাময়িক সমস্যা হয়েছে",
      description: "আমরা পেজটি এখন দেখাতে পারছি না। কিছুক্ষণ পর আবার চেষ্টা করুন।",
    },
    offline: {
      title: "আপনি অফলাইনে আছেন",
      description: "ইন্টারনেট সংযোগ ফিরলে এই পেজটি না হারিয়ে আবার চেষ্টা করুন।",
    },
    retry: "আবার চেষ্টা করুন",
    home: "হোমে ফিরুন",
    shop: "পণ্য দেখুন",
    loading: "পেজ লোড হচ্ছে…",
    commerceLoading: "নিরাপদ কেনাকাটার পেজ প্রস্তুত হচ্ছে…",
  },
  en: {
    page: {
      title: "This page cannot be displayed right now",
      description: "The issue has been contained to this page. Retry without losing your place.",
    },
    commerce: {
      title: "Secure shopping is temporarily unavailable",
      description: "Your cart and form details remain protected. Reconnect, then try again.",
    },
    global: {
      title: "Bojro paused unexpectedly",
      description: "An unexpected problem occurred. Restart this page safely.",
    },
    server: {
      title: "The server hit a temporary problem",
      description: "We cannot display this page right now. Please try again shortly.",
    },
    offline: {
      title: "You are offline",
      description: "Reconnect, then retry without losing this page.",
    },
    retry: "Try again",
    home: "Return home",
    shop: "Browse products",
    loading: "Loading this page…",
    commerceLoading: "Preparing the secure shopping page…",
  },
} as const;

export function normalizeLocale(value: string | string[] | undefined): AppLocale {
  return (Array.isArray(value) ? value[0] : value) === "en" ? "en" : "bn";
}
