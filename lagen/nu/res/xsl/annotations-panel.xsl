<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:template name="aside-annotations-panel">
    <xsl:param name="title"/> <!-- the heading of the panel -->
    <xsl:param name="badgecount"/> 
    <xsl:param name="nodeset"/> <!-- goes in the body of the panel -->
    <xsl:param name="paneltype"/>
    <xsl:param name="panelid"/>
    <xsl:param name="expanded" select="false()"/>
    <xsl:variable name="expanded-class"><xsl:if test="$expanded">in</xsl:if></xsl:variable>
    <div class="panel panel-default">
      <div class="panel-heading" role="tab" id="heading-{$paneltype}-{$panelid}">
	<h4 class="panel-title">
        <a role="button" data-toggle="collapse" data-parent="#panel-{$panelid}" href="#collapse-{$paneltype}-{$panelid}" aria-expanded="{$expanded}" aria-controls="collapse-{$paneltype}-{$panelid}">
	  <xsl:value-of select="$title"/>
	  <xsl:if test="$badgecount">
	    <span class="badge pull-right"><xsl:value-of select="$badgecount"/></span>
	  </xsl:if>
        </a>
      </h4>
    </div>
    <div id="collapse-{$paneltype}-{$panelid}" class="panel-collapse collapse {$expanded-class}" role="tabpanel" aria-labelledby="heading-{$paneltype}-{$panelid}">
      <div class="panel-body">
	<xsl:if test="$nodeset">
	  <!-- by using apply-templates rather than copy-of, we
	       transform the namespace from
	       http://www.w3.org/1999/xhtml to the default namespace
	       (and avoid declaring a whole mess of namespaces used in
	       the source doc) -->
	    <xsl:apply-templates select="$nodeset"/>
	  <!-- <xsl:copy-of select="$nodeset"/> -->
	</xsl:if>
      </div>
    </div>
  </div>    
  </xsl:template>
</xsl:stylesheet>
