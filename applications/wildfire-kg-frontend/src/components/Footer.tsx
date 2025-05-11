'use client'

export default function Footer() {
  return (
    <footer className="bg-[#1D2527] border-t border-gray-700 mt-auto">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="flex justify-center items-center">
          <p className="text-center text-sm leading-5 text-gray-300">
            Created and Managed by{' '}
            <a
              href="https://www.wildfirecommons.org/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white font-bold hover:text-gray-200 transition-colors"
            >
              Wildfire Science & Technology Commons
            </a>
          </p>
        </div>
      </div>
    </footer>
  )
} 