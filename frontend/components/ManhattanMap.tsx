// ManhattanMap.tsx
import React from 'react';

interface ManhattanMapProps {
  highlightedAreas: string[];
}

const ManhattanMap: React.FC<ManhattanMapProps> = ({ highlightedAreas }) => {
  const isHighlighted = (area: string) => {
    return highlightedAreas.some(a => 
      a.toLowerCase().includes(area.toLowerCase()) || 
      area.toLowerCase().includes(a.toLowerCase())
    );
  };

  return (
    <div className="relative mx-auto" style={{ maxWidth: '200px' }}>
      {/* Northern tip - very narrow */}
      <div className="mx-auto" style={{ width: '30%' }}>
        <div className={`p-1 text-xs text-center transition-colors ${
          isHighlighted('Inwood') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
        }`}
             style={{ fontSize: '9px', borderTopLeftRadius: '50%', borderTopRightRadius: '50%', border: '1px solid #e5e7eb' }}>
          Inwood
        </div>
      </div>
      
      {/* Washington Heights - widening */}
      <div className="mx-auto" style={{ width: '45%' }}>
        <div className={`p-1 text-xs text-center transition-colors ${
          isHighlighted('Washington Heights') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
        }`}
             style={{ fontSize: '9px', borderLeft: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb' }}>
          Washington Heights
        </div>
      </div>
      
      {/* Harlem - wider */}
      <div className="mx-auto" style={{ width: '65%' }}>
        <div className="grid grid-cols-2 gap-0">
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Harlem') || isHighlighted('West Harlem') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderLeft: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
            W. Harlem
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Harlem') || isHighlighted('East Harlem') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
            E. Harlem
          </div>
        </div>
      </div>
      
      {/* Central Park area with park in middle */}
      <div className="mx-auto" style={{ width: '85%' }}>
        <div className="grid grid-cols-5 gap-0">
          <div className={`col-span-2 p-2 text-xs text-center font-medium ${
            isHighlighted('Upper West Side') || isHighlighted('UWS') ? 'bg-purple-200 border-purple-400' : 'bg-purple-100'
          }`}
               style={{ fontSize: '9px', borderLeft: '1px solid #d8b4fe', borderBottom: '1px solid #d8b4fe' }}>
            Upper<br/>West Side
          </div>
          <div className="p-1 bg-green-200 text-xs text-center"
               style={{ fontSize: '7px', borderTop: '1px solid #86efac', borderBottom: '1px solid #86efac' }}>
            Central<br/>Park
          </div>
          <div className={`col-span-2 p-2 text-xs text-center font-medium ${
            isHighlighted('Upper East Side') || isHighlighted('UES') ? 'bg-purple-200 border-purple-400' : 'bg-purple-100'
          }`}
               style={{ fontSize: '9px', borderRight: '1px solid #d8b4fe', borderBottom: '1px solid #d8b4fe' }}>
            Upper<br/>East Side
          </div>
        </div>
      </div>
      
      {/* Midtown - widest part with curved edges */}
      <div className="mx-auto" style={{ width: '100%' }}>
        <div className="grid grid-cols-3 gap-0">
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted("Hell's Kitchen") ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderLeft: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb', borderBottomLeftRadius: '20%' }}>
            Hell's<br/>Kitchen
          </div>
          <div className={`p-2 text-xs text-center font-medium ${
            isHighlighted('Midtown') ? 'bg-purple-200 border-purple-400' : 'bg-purple-100'
          }`}
               style={{ fontSize: '9px', borderBottom: '1px solid #d8b4fe' }}>
            Midtown
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Murray Hill') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb', borderBottomRightRadius: '20%' }}>
            Murray<br/>Hill
          </div>
        </div>
      </div>
      
      {/* Chelsea to Flatiron - slight narrowing */}
      <div className="mx-auto" style={{ width: '95%' }}>
        <div className="grid grid-cols-3 gap-0">
          <div className={`p-1 text-xs text-center font-medium ${
            isHighlighted('Chelsea') ? 'bg-purple-200 border-purple-400' : 'bg-purple-100'
          }`}
               style={{ fontSize: '9px', borderLeft: '1px solid #d8b4fe', borderBottom: '1px solid #d8b4fe' }}>
            Chelsea
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Flatiron') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderBottom: '1px solid #e5e7eb' }}>
            Flatiron
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Gramercy') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
            Gramercy
          </div>
        </div>
      </div>
      
      {/* Villages */}
      <div className="mx-auto" style={{ width: '90%' }}>
        <div className="grid grid-cols-3 gap-0">
          <div className={`p-1 text-xs text-center font-medium ${
            isHighlighted('West Village') ? 'bg-purple-200 border-purple-400' : 'bg-purple-100'
          }`}
               style={{ fontSize: '9px', borderLeft: '1px solid #d8b4fe', borderBottom: '1px solid #d8b4fe' }}>
            West<br/>Village
          </div>
          <div className={`p-1 text-xs text-center font-medium ${
            isHighlighted('Greenwich Village') || isHighlighted('Greenwich') ? 'bg-purple-200 border-purple-400' : 'bg-purple-100'
          }`}
               style={{ fontSize: '9px', borderBottom: '1px solid #d8b4fe' }}>
            Greenwich<br/>Village
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('East Village') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
            East<br/>Village
          </div>
        </div>
      </div>
      
      {/* SoHo/Nolita/LES - continuing to narrow */}
      <div className="mx-auto" style={{ width: '85%' }}>
        <div className="grid grid-cols-3 gap-0">
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('SoHo') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderLeft: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
            SoHo
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Little Italy') || isHighlighted('Nolita') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderBottom: '1px solid #e5e7eb' }}>
            Little<br/>Italy
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Lower East Side') || isHighlighted('LES') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
            LES
          </div>
        </div>
      </div>
      
      {/* Tribeca/Chinatown - narrower */}
      <div className="mx-auto" style={{ width: '75%' }}>
        <div className="grid grid-cols-2 gap-0">
          <div className={`p-1 text-xs text-center font-medium ${
            isHighlighted('Tribeca') || isHighlighted('TriBeCa') ? 'bg-purple-200 border-purple-400' : 'bg-purple-100'
          }`}
               style={{ fontSize: '9px', borderLeft: '1px solid #d8b4fe', borderBottom: '1px solid #d8b4fe' }}>
            Tribeca
          </div>
          <div className={`p-1 text-xs text-center transition-colors ${
            isHighlighted('Chinatown') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
          }`}
               style={{ fontSize: '9px', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
            Chinatown
          </div>
        </div>
      </div>
      
      {/* Financial District - narrowing to tip */}
      <div className="mx-auto" style={{ width: '50%' }}>
        <div className={`p-1 text-xs text-center transition-colors ${
          isHighlighted('Financial District') || isHighlighted('FiDi') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
        }`}
             style={{ fontSize: '9px', borderLeft: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
          FiDi
        </div>
      </div>
      
      {/* Battery Park - very tip */}
      <div className="mx-auto" style={{ width: '25%' }}>
        <div className={`p-0.5 text-xs text-center transition-colors ${
          isHighlighted('Battery') || isHighlighted('Battery Park') ? 'bg-purple-100 border-purple-300' : 'bg-gray-100'
        }`}
             style={{ fontSize: '8px', borderBottomLeftRadius: '50%', borderBottomRightRadius: '50%', borderLeft: '1px solid #e5e7eb', borderRight: '1px solid #e5e7eb', borderBottom: '1px solid #e5e7eb' }}>
          Battery
        </div>
      </div>
    </div>
  );
};

export default ManhattanMap;