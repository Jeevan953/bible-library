export const VERSION_GROUPS = {
  'Modern Translations': [
    { code: 'NIV', name: 'New International Version', year: 2011 },
    { code: 'ESV', name: 'English Standard Version', year: 2016 },
    { code: 'NLT', name: 'New Living Translation', year: 2015 },
    { code: 'CSB', name: 'Christian Standard Bible', year: 2017 },
    { code: 'NASB', name: 'New American Standard Bible', year: 2020 },
    { code: 'RSV', name: 'Revised Standard Version', year: 1952 },
    { code: 'GNT', name: 'Good News Translation', year: 1992 },
    { code: 'AMP', name: 'Amplified Bible', year: 2015 },
    { code: 'MSG', name: 'The Message Bible', year: 2002 },
    { code: 'TLB', name: 'The Living Bible', year: 1971 },
    { code: 'NET', name: 'New English Translation', year: 2017 },
  ],
  'Historical Translations': [
    { code: 'KJV', name: 'King James Version', year: 1611 },
    { code: 'ASV', name: 'American Standard Version', year: 1901 },
    { code: 'WEB', name: 'World English Bible', year: 2023 },
    // ... your existing historical versions
  ],
  // ... your other groups
};

// Get all versions for dropdowns
export const ALL_VERSIONS = [
  ...VERSION_GROUPS['Modern Translations'],
  ...VERSION_GROUPS['Historical Translations'],
  // ... other groups
];