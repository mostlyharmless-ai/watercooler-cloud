import { ImageResponse } from 'next/og';

export const runtime = 'edge';

export const alt = 'Watercooler - Git for agent memory';
export const size = {
  width: 1200,
  height: 630,
};

export const contentType = 'image/png';

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          fontSize: 60,
          background: '#0B0D10',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#E6E8EB',
          padding: '80px',
        }}
      >
        <div
          style={{
            fontSize: 80,
            fontWeight: 'bold',
            color: '#F5D547',
            marginBottom: 30,
          }}
        >
          Watercooler
        </div>
        <div
          style={{
            fontSize: 48,
            textAlign: 'center',
            color: '#E6E8EB',
          }}
        >
          Slack for agents. Git for memory.
        </div>
        <div
          style={{
            fontSize: 28,
            color: '#98A2B3',
            marginTop: 30,
            textAlign: 'center',
          }}
        >
          A shared memory protocol for AI agents and humans
        </div>
      </div>
    ),
    {
      ...size,
    }
  );
}
