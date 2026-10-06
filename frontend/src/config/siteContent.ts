type InformationItem = { title: string; description: string }

export type SiteContent = {
  brand: { name: string; description: string }
  login: {
    heading: string
    description: string
    information: InformationItem[]
    formHeading: string
    formDescription: string
    accessHelp: string
    footer: string
  }
}

export const defaultSiteContent: SiteContent = {
  brand: { name: 'CAP', description: '' },
  login: {
    heading: 'Compliance records',
    description: 'Sign in to view requirements, reviews, and evidence.',
    information: [],
    formHeading: 'Sign in',
    formDescription: 'Enter your account email and password.',
    accessHelp: 'Contact an administrator if you need an account.',
    footer: 'Compliance system',
  },
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function text(value: unknown, fallback: string, maxLength = 240): string {
  return typeof value === 'string' && value.trim() && value.length <= maxLength
    ? value.trim()
    : fallback
}

export function parseSiteContent(value: unknown): SiteContent {
  const input = record(value)
  const brand = record(input.brand)
  const login = record(input.login)
  const information = Array.isArray(login.information)
    ? login.information.slice(0, 4).map((item) => {
      const entry = record(item)
      return {
        title: text(entry.title, '', 80),
        description: text(entry.description, '', 160),
      }
    }).filter((item) => item.title && item.description)
    : defaultSiteContent.login.information

  return {
    brand: {
      name: text(brand.name, defaultSiteContent.brand.name, 60),
      description: text(brand.description, '', 100),
    },
    login: {
      heading: text(login.heading, defaultSiteContent.login.heading, 100),
      description: text(login.description, defaultSiteContent.login.description),
      information,
      formHeading: text(login.formHeading, defaultSiteContent.login.formHeading, 80),
      formDescription: text(login.formDescription, defaultSiteContent.login.formDescription),
      accessHelp: text(login.accessHelp, defaultSiteContent.login.accessHelp),
      footer: text(login.footer, defaultSiteContent.login.footer, 100),
    },
  }
}
