<!-- ecc:skills/frontend-slides @25278e7d -->
# ECC provenance note

ECC's slide skill converts an existing PPTX into a web deck. Here that path is: read the
.pptx with `anthropic-skills:pptx`, then rebuild the content with this skill's HTML layouts
(one slide per section, tokens from the design system). Note only: nothing else to graft.
