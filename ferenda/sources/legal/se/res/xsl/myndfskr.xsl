<?xml version="1.0" encoding="utf-8"?>
<!--
Note: this template expects XHTML1.1, outputs HTML5

It's an adapted version of paged.xsl with extra support for a metadata
sidebar + non-paged (ie. structural) XHTML
-->

<xsl:stylesheet version="1.0"
		xmlns:xhtml="http://www.w3.org/1999/xhtml"
		xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
		xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
		xmlns:dcterms="http://purl.org/dc/terms/"
		xmlns:rinfo="http://rinfo.lagrummet.se/taxo/2007/09/rinfo/pub#"
		xmlns:rinfoex="http://lagen.nu/terms#"
		xmlns:ext="http://exslt.org/common"
		exclude-result-prefixes="xhtml rdf dcterms rinfo rinfoex">
  <xsl:import href="annotations-panel.xsl"/>
  <xsl:include href="base.xsl"/>

  <xsl:template name="headtitle"><xsl:value-of select="xhtml:title"/></xsl:template>
  <xsl:template name="metarobots"><xsl:comment>Robot metatag goes here</xsl:comment></xsl:template>
  <xsl:template name="linkalternate"><xsl:comment>Alternate link(s)</xsl:comment></xsl:template>
  <xsl:template name="headmetadata"><xsl:comment>headmetadata?</xsl:comment></xsl:template>
  <xsl:template name="bodyclass">myndfskr</xsl:template>
  <xsl:template name="pagetitle">
    <xsl:variable name="metadata">
      <ul>
	<li><a href="{//xhtml:head/xhtml:link[@rel='prov:alternateOf']/@href}">Källa</a></li>
	<li>Senast hämtad (entry:orig_updated)</li>
	<li>(Om konsoliderad: konsolideringsdatum</li>
	<li>(Om konsoliderad: konsolideringsunderlag m länkar)</li>
	<li>Om grundförfattning: OBS efterförljande ändringsförfattning</li>
	<li>Om inte senaste ändringsförfattning: OBS efterförljande ändringsförfattning</li>
	<li>Om ändringsförfattning: länk t grundförfattning</li>
	<li>Om grund- eller ändringsförfattning: Länk t konsoliderad version, om det finns</li>
      </ul>
    </xsl:variable>
    <div class="row">
      <section id="top" class="col-sm-7">
      <h1><xsl:value-of select="../xhtml:head/xhtml:meta[@property='dcterms:identifier']/@content"/></h1>
      <h2><xsl:value-of select="../xhtml:head/xhtml:title"/></h2>
      </section>
      <aside class="panel-group col-sm-5" role="tablist" id="panel-top" aria-multiselectable="true">
	<xsl:call-template name="aside-annotations-panel">
	  <xsl:with-param name="title">Metadata</xsl:with-param>
	  <xsl:with-param name="badgecount"/>
	  <xsl:with-param name="panelid">top</xsl:with-param>
	  <xsl:with-param name="paneltype">metadata</xsl:with-param>
	  <xsl:with-param name="expanded" select="true()"/>
	  <xsl:with-param name="nodeset" select="ext:node-set($metadata)"/>
	</xsl:call-template>
      </aside>
    </div>
  </xsl:template>
  <xsl:param name="dyntoc" select="true()"/>
  <xsl:param name="fixedtoc" select="true()"/>
  <xsl:param name="content-under-pagetitle" select="false()"/>

  <xsl:template match="xhtml:div[@class='pdfpage']">
    <div class="page">
      <!-- Nav tabs -->
      <ul class="nav nav-tabs">
	<li class="active"><a href="#{@id}-text" class="view-text"><xsl:value-of select="@id"/></a></li>
	<li><a href="#{@id}-img" class="view-img"><span class="glyphicon glyphicon-picture">&#160;</span>Original</a></li>
      </ul>
      <div class="pdfpage" id="{@id}" style="{@style}">
	<a href="{@src}" class="facsimile"><img data-src="{@src}"/></a>
	<xsl:apply-templates/>
      </div>
      <!--
      <div class="annotations">
	<p>Annotated content for <xsl:value-of select="@id"/> goes here</p>
	</div>
      -->
    </div>
  </xsl:template>

  <xsl:template match="xhtml:body/xhtml:div[@class!='pdfpage']">
    <!-- ie any other documnent wrapper element except .pdfpage,
         mostly used to keep pagewidth down -->
    <section id="top" class="col-sm-7">
      <xsl:apply-templates/>
    </section>
    <aside class="col-sm-5">&#160;</aside>
  </xsl:template>

  <!-- default rule: Identity transform -->
  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- toc handling, just list all available pages for now -->
  <xsl:template match="xhtml:div[@class='pdfpage']" mode="toc">
    <li><a href="#{@id}"><xsl:value-of select="@id"/></a></li>
  </xsl:template>

  <!-- toc handling (do nothing) -->
  <xsl:template match="@*|node()" mode="toc"/>
  
</xsl:stylesheet>

