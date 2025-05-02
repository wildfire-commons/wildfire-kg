'use client';

export default function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-8">About Wildfire Knowledge Graph</h1>
      
      <div className="prose prose-lg">
        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-4">Project Overview</h2>
          <p className="mb-4">
            The Wildfire Knowledge Graph project is a collaborative research initiative started by five graduate students at the University of California San Diego (UCSD). 
            This project aims to develop a comprehensive knowledge graph system for wildfire data analysis and management.
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-4">Research Team</h2>
          <div className="mb-6">
            <h3 className="text-xl font-medium mb-2">Graduate Students</h3>
            <ul className="list-disc pl-6 mb-4 space-y-4">
              <li>
                <strong>Nick Scherer</strong>
                <ul className="list-none pl-4 mt-1">
                  <li>
                    Tech Lead at{" "}
                    <a 
                      href="https://rostrumrecords.com/" 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-800 underline"
                    >
                      Rostrum Pacific
                    </a>{" "}
                    /{" "}
                    <a 
                      href="https://www.spaceheatermusic.io/" 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-800 underline"
                    >
                      SpaceHeater
                    </a>
                  </li>
                  <li>Project Lead/Platform Engineer: Bridging data, software, and leadership to empower land and fire managers.</li>
                </ul>
              </li>
              <li>
                <strong>Blake Crowler</strong>
                <ul className="list-none pl-4 mt-1">
                  <li>Data Scientist at Viasat</li>
                  <li>Project Architect/AI Engineer: AI/ML Integration</li>
                </ul>
              </li>
              <li>
                <strong>Jennifer Du</strong>
                <ul className="list-none pl-4 mt-1">
                  <li>TODO: Fill in</li>
                  <li>Data Engineer: TODO: Fill in</li>
                </ul>
              </li>
              <li>
                <strong>Pitchayarasm Kunghae</strong>
                <ul className="list-none pl-4 mt-1">
                  <li>TODO: Fill in</li>
                  <li>Data Engineer & Integrations: TODO: Fill in</li>
                </ul>
              </li>
              <li>
                <strong>Wesley Schiller</strong>
                <ul className="list-none pl-4 mt-1">
                  <li>TODO: Fill in</li>
                  <li>Ontology & Data Modeling: TODO: Fill in</li>
                </ul>
              </li>
            </ul>
          </div>
          
          <div>
            <h3 className="text-xl font-medium mb-2">Faculty Advisors</h3>
            <ul className="list-disc pl-6">
              <li>Prof. Ilkay Altintas - SDSC Chief Data Science Officer</li>
              <li>Prof. Mai Nguyen - SDSC Lead for Data Analytics</li>
              <li>Issac Nealy - PhD Candidate, UCSD, Immersive Forest Research</li>
            </ul>
          </div>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-4">Project Goals</h2>
          <ul className="list-disc pl-6">
            <li className="mb-2">Develop a comprehensive knowledge graph for wildfire data integration</li>
            <li className="mb-2">Create intelligent systems for wildfire analysis and prediction</li>
            <li className="mb-2">Provide tools for fire managers, land managers, burn bosses and researchers to make better decisions about proactive wildfire management</li>
            <li className="mb-2">Advance the field of environmental data science through innovative AI applications</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-4">Resources</h2>
          <div className="space-y-2">
            <p>
              <strong>Source Code:</strong>{" "}
              <a 
                href="https://github.com/wildfire-commons/wildfire-kg" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-800 underline"
              >
                GitHub Repository
              </a>
            </p>
          </div>
        </section>

        <section>
          <h2 className="text-2xl font-semibold mb-4">Contact</h2>
          <p>
            For more information about the project or collaboration opportunities, please contact us at{" "}
            <a 
              href="mailto:ialtintas@ucsd.edu" 
              className="text-blue-600 hover:text-blue-800 underline"
            >
              ialtintas@ucsd.edu
            </a>
          </p>
        </section>
      </div>
    </div>
  );
} 